from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare, format_amount


class CpqConfigureWizard(models.TransientModel):
    _name = 'cpq.configure.wizard'
    _description = 'Configure a product'

    order_id = fields.Many2one('sale.order', required=True)
    configurator_id = fields.Many2one('cpq.configurator', required=True,
                                      domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]")
    company_id = fields.Many2one(related='order_id.company_id')
    currency_id = fields.Many2one(related='order_id.currency_id')
    quantity = fields.Float(default=1.0, required=True, digits='Product Unit')
    line_ids = fields.One2many('cpq.configure.wizard.line', 'wizard_id', compute='_compute_line_ids',
                               store=True, readonly=False)
    total_price = fields.Monetary("Unit price", compute='_compute_pricing', currency_field='currency_id')
    breakdown_html = fields.Html(compute='_compute_pricing', sanitize=False)
    problems = fields.Text(compute='_compute_pricing')
    description = fields.Html(related='configurator_id.description')

    @api.depends('configurator_id')
    def _compute_line_ids(self):
        for wizard in self:
            options = wizard.configurator_id.option_ids.sorted(lambda o: (o.section_id.sequence, o.sequence, o.id))
            wizard.line_ids = [(5, 0, 0)] + [(0, 0, {
                'option_id': option.id,
                'selected': option.default_selected,
                'quantity': option.default_qty,
            }) for option in options]

    # ------------------------------------------------------------------
    # Rules and pricing (live: everything is computed from the lines)
    # ------------------------------------------------------------------
    def _selected_lines(self):
        return self.line_ids.filtered(lambda l: l.selected and l.available)

    def _check_rules(self):
        """Return the list of problems that prevent adding the configuration."""
        self.ensure_one()
        problems = []
        selected = self._selected_lines()
        options = selected.option_id
        for section in self.configurator_id.section_ids:
            count = len(selected.filtered(lambda l, s=section: l.option_id.section_id == s))
            if section.required and not count:
                problems.append(_("%s: choose an option.", section.name))
            if section.selection == 'one' and count > 1:
                problems.append(_("%s: only one option can be chosen.", section.name))
        for line in selected:
            option = line.option_id
            if float_compare(line.quantity, option.min_qty, precision_digits=4) < 0 or \
                    (option.max_qty and float_compare(line.quantity, option.max_qty, precision_digits=4) > 0):
                problems.append(_("%(option)s: quantity must be between %(min)s and %(max)s.",
                                  option=option.name, min=option.min_qty, max=option.max_qty or '∞'))
            for excluded in option.excluded_option_ids & options:
                if option.id < excluded.id or option not in excluded.excluded_option_ids:
                    problems.append(_("%(a)s is not compatible with %(b)s.", a=option.name, b=excluded.name))
            if option.required_option_ids and not option.required_option_ids & options:
                problems.append(_("%(option)s requires %(required)s.", option=option.name,
                                  required=_(" or ").join(option.required_option_ids.mapped('name'))))
        for line in self.line_ids.filtered(lambda l: l.selected and not l.available):
            problems.append(_("%(option)s is only available with %(trigger)s.", option=line.option_id.name,
                              trigger=_(" or ").join(line.option_id.visible_if_option_ids.mapped('name'))))
        if self.quantity <= 0:
            problems.append(_("Quantity must be positive."))
        return problems

    def _price_details(self):
        """(rows, rules, total): option rows, applied price rules, unit price."""
        self.ensure_one()
        selected = self._selected_lines()
        rows = [(line.option_id.section_id.name, line.option_id.name, line.quantity, line.option_id.unit_price,
                 line.option_id.unit_price * line.quantity) for line in selected]
        subtotal = self.configurator_id.base_price + sum(r[4] for r in rows)
        rules = []
        total = subtotal
        for rule in self.configurator_id.price_rule_ids:
            if not rule._applies(selected.option_id, self.quantity):
                continue
            if rule.rule_type == 'fixed':
                amount = rule.amount
            elif rule.rule_type == 'percent':
                amount = total * rule.amount / 100.0
            else:
                amount = -total * rule.amount / 100.0
            total += amount
            rules.append((rule.name, amount))
        return rows, rules, total

    @api.depends('line_ids.selected', 'line_ids.quantity', 'quantity', 'configurator_id')
    def _compute_pricing(self):
        for wizard in self:
            if not wizard.configurator_id:
                wizard.update({'total_price': 0.0, 'breakdown_html': False, 'problems': False})
                continue
            rows, rules, total = wizard._price_details()
            currency = wizard.currency_id or wizard.env.company.currency_id

            def money(value):
                return format_amount(wizard.env, value, currency)
            body = [Markup('<tr><td colspan="3">%s</td><td class="text-end">%s</td></tr>') % (
                _("Base price"), money(wizard.configurator_id.base_price))]
            for section, option, qty, unit, subtotal in rows:
                body.append(Markup('<tr><td class="text-muted">%s</td><td>%s</td><td class="text-end">%s × %s</td>'
                                   '<td class="text-end">%s</td></tr>') % (section, option, qty, money(unit), money(subtotal)))
            for name, amount in rules:
                body.append(Markup('<tr class="text-info"><td colspan="3">%s</td><td class="text-end">%s</td></tr>') % (
                    name, money(amount)))
            body.append(Markup('<tr class="fw-bold"><td colspan="3">%s</td><td class="text-end">%s</td></tr>') % (
                _("Unit price"), money(total)))
            body.append(Markup('<tr class="text-muted"><td colspan="3">%s</td><td class="text-end">%s</td></tr>') % (
                _("Total for %s unit(s)", wizard.quantity), money(total * wizard.quantity)))
            wizard.breakdown_html = Markup('<table class="table table-sm mb-0">%s</table>') % Markup('').join(body)
            wizard.total_price = total
            problems = wizard._check_rules()
            wizard.problems = '\n'.join(problems) if problems else False

    def _summary(self):
        lines = [self.configurator_id.name]
        for line in self._selected_lines():
            qty = f" × {line.quantity:g}" if line.quantity != 1 else ''
            lines.append(f"- {line.option_id.section_id.name}: {line.option_id.name}{qty}")
        return '\n'.join(lines)

    def action_add_to_order(self):
        self.ensure_one()
        if self.order_id.state not in ('draft', 'sent'):
            raise UserError(_("Configured products can only be added to quotations."))
        problems = self._check_rules()
        if problems:
            raise UserError(_("Please fix the configuration:\n%s", '\n'.join(problems)))
        rows, rules, total = self._price_details()
        configuration = self.env['cpq.configuration'].create({
            'configurator_id': self.configurator_id.id,
            'order_id': self.order_id.id,
            'quantity': self.quantity,
            'price_unit': total,
            'summary': self._summary(),
            'line_ids': [(0, 0, {
                'sequence': index, 'section_name': line.option_id.section_id.name, 'option_id': line.option_id.id,
                'product_id': line.option_id.product_id.id, 'quantity': line.quantity,
                'unit_price': line.option_id.unit_price, 'subtotal': line.option_id.unit_price * line.quantity,
            }) for index, line in enumerate(self._selected_lines())],
        })
        configuration._create_product_and_bom()
        sale_line = self.env['sale.order.line'].create({
            'order_id': self.order_id.id,
            'product_id': configuration.product_id.id,
            'name': configuration.summary,
            'product_uom_qty': self.quantity,
            'cpq_configuration_id': configuration.id,
        })
        sale_line.price_unit = total
        configuration.sale_line_id = sale_line
        return {'type': 'ir.actions.act_window_close'}


class CpqConfigureWizardLine(models.TransientModel):
    _name = 'cpq.configure.wizard.line'
    _description = 'Configure a product: option'
    _order = 'id'

    wizard_id = fields.Many2one('cpq.configure.wizard', required=True, ondelete='cascade')
    option_id = fields.Many2one('cpq.option', required=True)
    section_name = fields.Char(related='option_id.section_id.name', string="Step")
    product_id = fields.Many2one(related='option_id.product_id')
    unit_price = fields.Float(related='option_id.unit_price')
    selected = fields.Boolean()
    quantity = fields.Float(default=1.0, digits='Product Unit')
    available = fields.Boolean(compute='_compute_available', help="False when its 'only available with' options are not chosen.")
    stock_qty = fields.Float("In stock", compute='_compute_stock_qty', digits='Product Unit')
    stock_ok = fields.Boolean(compute='_compute_stock_qty')

    @api.depends('wizard_id.line_ids.selected', 'option_id.visible_if_option_ids')
    def _compute_available(self):
        for line in self:
            triggers = line.option_id.visible_if_option_ids
            chosen = line.wizard_id.line_ids.filtered('selected').option_id
            line.available = not triggers or bool(triggers & chosen)

    @api.depends('product_id', 'quantity', 'wizard_id.quantity')
    def _compute_stock_qty(self):
        for line in self:
            product = line.product_id
            line.stock_qty = product.free_qty if product.is_storable else 0.0
            line.stock_ok = not product.is_storable or product.free_qty >= line.quantity * (line.wizard_id.quantity or 1)
