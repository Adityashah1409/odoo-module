from odoo import api, fields, models

from .name_tools import clean


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    contact_first_name = fields.Char('Contact first name')
    contact_last_name = fields.Char('Contact last name')

    def _lead_names_prepare(self, vals):
        Partner = self.env['res.partner']
        if 'contact_first_name' in vals or 'contact_last_name' in vals:
            first = clean(vals['contact_first_name'] if 'contact_first_name' in vals
                          else self[:1].contact_first_name)
            last = clean(vals['contact_last_name'] if 'contact_last_name' in vals else self[:1].contact_last_name)
            name = Partner._partner_names_join(first, '', last)
            if name:
                vals['contact_name'] = name
        elif vals.get('contact_name'):
            parts = Partner._partner_names_split(vals['contact_name'])
            given = ' '.join(filter(None, [parts['first_name'], parts['middle_name']]))
            vals.update({'contact_first_name': given or False, 'contact_last_name': parts['last_name']})
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self.browse()._lead_names_prepare(dict(vals)) for vals in vals_list])

    def write(self, vals):
        if ('contact_first_name' in vals or 'contact_last_name' in vals) and len(self) > 1:
            for lead in self:
                super(CrmLead, lead).write(lead._lead_names_prepare(dict(vals)))
            return True
        if 'contact_first_name' in vals or 'contact_last_name' in vals or 'contact_name' in vals:
            vals = self[:1]._lead_names_prepare(dict(vals))
        return super().write(vals)

    @api.onchange('contact_first_name', 'contact_last_name')
    def _onchange_lead_names_parts(self):
        for lead in self:
            name = self.env['res.partner']._partner_names_join(lead.contact_first_name, '', lead.contact_last_name)
            if name and name != clean(lead.contact_name):
                lead.contact_name = name

    @api.onchange('contact_name')
    def _onchange_lead_names_name(self):
        for lead in self.filtered('contact_name'):
            current = self.env['res.partner']._partner_names_join(lead.contact_first_name, '', lead.contact_last_name)
            if clean(lead.contact_name) != current:
                lead.update(lead._lead_names_prepare({'contact_name': lead.contact_name}))

    def _prepare_customer_values(self, partner_name, is_company=False, parent_id=False):
        values = super()._prepare_customer_values(partner_name, is_company=is_company, parent_id=parent_id)
        if not is_company and partner_name and partner_name == self.contact_name \
                and (self.contact_first_name or self.contact_last_name):
            values.update({'first_name': self.contact_first_name, 'last_name': self.contact_last_name})
        return values
