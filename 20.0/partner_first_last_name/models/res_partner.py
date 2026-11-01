from odoo import api, fields, models

from .name_tools import clean, join_name, split_name

PARAM = 'partner_first_last_name.'
PARTS = ('first_name', 'middle_name', 'last_name')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    first_name = fields.Char('First name', index='btree_not_null')
    middle_name = fields.Char('Middle name')
    last_name = fields.Char('Last name', index='btree_not_null')
    partner_names_show_middle = fields.Boolean(compute='_compute_partner_names_show_middle')

    def _compute_partner_names_show_middle(self):
        show = self._partner_names_settings()[1]
        for partner in self:
            partner.partner_names_show_middle = show or bool(partner.middle_name)

    # ------------------------------------------------------------------
    # settings
    # ------------------------------------------------------------------
    @api.model
    def _partner_names_settings(self):
        ICP = self.env['ir.config_parameter'].sudo()
        order = ICP.get_str(PARAM + 'order') or 'first_last'
        middle = ICP.get_bool(PARAM + 'middle')
        return order, middle

    @api.model
    def _partner_names_join(self, first, middle, last):
        return join_name(first, middle, last, self._partner_names_settings()[0])

    @api.model
    def _partner_names_split(self, name, order=None):
        current_order, middle = self._partner_names_settings()
        first, middle_name, last = split_name(name, order or current_order, middle)
        return {'first_name': first or False, 'middle_name': middle_name or False, 'last_name': last or False}

    # ------------------------------------------------------------------
    # keeping name and parts together
    # ------------------------------------------------------------------
    @api.model
    def _partner_names_is_person(self, vals, record=None):
        """Odoo 20: a company is its own commercial entity with a VAT number (``is_company`` is computed that
        way, and the Contacts app opens new records with ``default_is_company``), so decide from VAT and parent:
        contacts of a company share its VAT but are people."""
        vat = vals['vat'] if 'vat' in vals else (record.vat if record else False)
        parent = vals['parent_id'] if 'parent_id' in vals else (record.parent_id.id if record else False)
        return bool(parent) or not (vat and vat not in ('/', 'na', 'NA'))

    def _partner_names_can_split(self, vals, record=None):
        """Can a plain name be split into parts?

        Odoo 20 has no person / company switch (``is_company`` comes from the VAT), so a name alone could be a
        company: only names of company contacts, users and contacts that already have parts are split."""
        if self.env.context.get('partner_names_person'):
            return True
        parent = vals['parent_id'] if 'parent_id' in vals else (record.parent_id.id if record else False)
        return bool(parent or (record and (record.user_ids or record.first_name or record.last_name)))

    @api.model
    def _partner_names_people_domain(self):
        return [('name', '!=', False), '|', ('has_vat', '=', False), ('parent_id', '!=', False),
                '|', '|', ('parent_id', '!=', False), ('user_ids', '!=', False),
                '|', ('first_name', '!=', False), ('last_name', '!=', False)]

    def _partner_names_prepare(self, vals):
        """Complete ``vals`` (for ``self``, possibly empty): name from the parts, or parts from the name."""
        if self.env.context.get('partner_names_skip') or not self._partner_names_is_person(vals, self[:1] or None):
            return vals
        if any(key in vals for key in PARTS):
            parts = {key: clean(vals[key]) if key in vals else (self[:1][key] or '') for key in PARTS}
            for key in PARTS:
                if key in vals:
                    vals[key] = parts[key] or False
            name = self._partner_names_join(parts['first_name'], parts['middle_name'], parts['last_name'])
            if name:
                vals['name'] = name
        elif vals.get('name') and self._partner_names_can_split(vals, self[:1] or None):
            vals.update(self._partner_names_split(vals['name']))
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self.browse()._partner_names_prepare(dict(vals)) for vals in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get('partner_names_skip') or not (
                any(key in vals for key in PARTS) or 'name' in vals):
            return super().write(vals)
        if any(key in vals for key in PARTS) and len(self) > 1:
            # the name depends on the other parts of each record
            for partner in self:
                super(ResPartner, partner).write(partner._partner_names_prepare(dict(vals)))
            return True
        return super().write(self[:1]._partner_names_prepare(dict(vals)) if len(self) == 1
                             else self.browse()._partner_names_prepare(dict(vals)))

    @api.onchange('first_name', 'middle_name', 'last_name')
    def _onchange_partner_names_parts(self):
        for partner in self.filtered(lambda p: p.parent_id or not p.has_vat):
            name = partner._partner_names_join(partner.first_name, partner.middle_name, partner.last_name)
            if name and name != clean(partner.name):
                partner.name = name

    @api.onchange('name')
    def _onchange_partner_names_name(self):
        for partner in self.filtered(lambda p: (p.parent_id or not p.has_vat) and p.name):
            current = partner._partner_names_join(partner.first_name, partner.middle_name, partner.last_name)
            if clean(partner.name) != current and partner._partner_names_can_split({}, partner):
                partner.update(partner._partner_names_split(partner.name))

    # ------------------------------------------------------------------
    # mass actions
    # ------------------------------------------------------------------
    @api.model
    def _partner_names_people(self, domain=None):
        return self.with_context(active_test=False).search(self._partner_names_people_domain() + (domain or []))

    @api.model
    def _partner_names_fill_missing(self, order=None):
        """Split the name of the people that have no name parts yet (names written in ``order``)."""
        people = self._partner_names_people([('first_name', '=', False), ('last_name', '=', False)])
        for partner in people:
            partner.with_context(partner_names_skip=True).write(partner._partner_names_split(partner.name, order))
        return len(people)

    @api.model
    def _partner_names_apply_order(self, previous_order=None):
        """Rewrite the names of all people with the current order (from their parts).

        Names without parts are first split with ``previous_order``, the order they were written in."""
        count = self._partner_names_fill_missing(previous_order)
        people = self._partner_names_people([('first_name', '!=', False)]) | \
            self._partner_names_people([('last_name', '!=', False)])
        changed = 0
        for partner in people:
            name = partner._partner_names_join(partner.first_name, partner.middle_name, partner.last_name)
            if name and name != partner.name:
                partner.with_context(partner_names_skip=True).write({'name': name})
                changed += 1
        return count, changed

    def action_partner_names_split(self):
        """Contacts list action: split the name again into its parts."""
        for partner in self.filtered(lambda p: (p.parent_id or not p.has_vat) and p.name):
            partner.with_context(partner_names_skip=True).write(partner._partner_names_split(partner.name))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': self.env._('Names split for %s contact(s).', len(self)), 'type': 'success',
                           'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}
