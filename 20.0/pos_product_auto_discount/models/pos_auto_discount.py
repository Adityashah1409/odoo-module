from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PosAutoDiscount(models.Model):
    _name = 'pos.auto.discount'
    _description = 'POS Automatic Discount'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    discount = fields.Float('Discount (%)', required=True, digits=(16, 2))
    applies_on = fields.Selection([
        ('products', 'Products'),
        ('categories', 'POS categories'),
        ('all', 'All products'),
    ], required=True, default='products')
    product_tmpl_ids = fields.Many2many(
        'product.template', string='Products', domain=[('available_in_pos', '=', True)])
    pos_categ_ids = fields.Many2many(
        'pos.category', string='POS Categories', help='Sub-categories are included.')
    min_qty = fields.Float(
        'Minimum quantity', default=0.0, digits='Product Unit',
        help='The line quantity must reach this value. 0 = any quantity.')
    date_from = fields.Date('Start date')
    date_to = fields.Date('End date')
    hour_from = fields.Float('From hour', help='Happy hour start (local time of the register). Leave both hours at 0 for all day.')
    hour_to = fields.Float('To hour', help='Happy hour end (excluded). An end before the start crosses midnight.')
    config_ids = fields.Many2many(
        'pos.config', string='Points of Sale', help='Leave empty to apply in every point of sale.')
    status = fields.Selection([
        ('running', 'Running'), ('scheduled', 'Scheduled'), ('expired', 'Expired'),
    ], compute='_compute_status')
    line_ids = fields.One2many('pos.order.line', 'auto_discount_id', string='Order lines', readonly=True)
    line_count = fields.Integer(compute='_compute_stats')
    discount_amount = fields.Monetary(compute='_compute_stats', string='Discount given', currency_field='currency_id')
    currency_id = fields.Many2one(related='company_id.currency_id')

    _discount_range = models.Constraint(
        'CHECK(discount > 0 AND discount <= 100)', 'The discount must be between 0 and 100%.')
    _min_qty_positive = models.Constraint('CHECK(min_qty >= 0)', 'The minimum quantity cannot be negative.')

    @api.depends('date_from', 'date_to')
    def _compute_status(self):
        today = fields.Date.context_today(self)
        for rule in self:
            if rule.date_to and rule.date_to < today:
                rule.status = 'expired'
            elif rule.date_from and rule.date_from > today:
                rule.status = 'scheduled'
            else:
                rule.status = 'running'

    @api.depends('line_ids.auto_discount_amount')
    def _compute_stats(self):
        stats = {
            rule.id: (count, amount)
            for rule, count, amount in self.env['pos.order.line']._read_group(
                [('auto_discount_id', 'in', self.ids)], ['auto_discount_id'], ['__count', 'auto_discount_amount:sum'])
        }
        for rule in self:
            rule.line_count, rule.discount_amount = stats.get(rule.id, (0, 0.0))

    @api.constrains('date_from', 'date_to', 'hour_from', 'hour_to', 'applies_on', 'product_tmpl_ids', 'pos_categ_ids')
    def _check_rule(self):
        for rule in self:
            if rule.date_from and rule.date_to and rule.date_from > rule.date_to:
                raise ValidationError(self.env._('%s: the end date is before the start date.', rule.name))
            if not (0 <= rule.hour_from <= 24 and 0 <= rule.hour_to <= 24):
                raise ValidationError(self.env._('%s: hours must be between 0 and 24.', rule.name))
            if rule.applies_on == 'products' and not rule.product_tmpl_ids:
                raise ValidationError(self.env._('%s: choose at least one product.', rule.name))
            if rule.applies_on == 'categories' and not rule.pos_categ_ids:
                raise ValidationError(self.env._('%s: choose at least one POS category.', rule.name))

    @api.model
    def _rules_for_config(self, config):
        """Rules a register may apply: active, for this POS (or all), same company, not expired."""
        today = fields.Date.context_today(self)
        return self.search([
            ('company_id', '=', config.company_id.id),
            '|', ('config_ids', '=', False), ('config_ids', 'in', config.ids),
            '|', ('date_to', '=', False), ('date_to', '>=', today),
        ])

    def _pos_data(self):
        return [{
            'id': rule.id,
            'name': rule.name,
            'sequence': rule.sequence,
            'discount': rule.discount,
            'applies_on': rule.applies_on,
            'product_tmpl_ids': rule.product_tmpl_ids.ids,
            'pos_categ_ids': rule.pos_categ_ids.ids,
            'min_qty': rule.min_qty,
            'date_from': fields.Date.to_string(rule.date_from) if rule.date_from else False,
            'date_to': fields.Date.to_string(rule.date_to) if rule.date_to else False,
            'hour_from': rule.hour_from,
            'hour_to': rule.hour_to,
        } for rule in self]

    def action_view_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Discounted lines: %s', self.name),
            'res_model': 'pos.order.line',
            'view_mode': 'list',
            'views': [(self.env.ref('pos_product_auto_discount.pos_order_line_auto_discount_list').id, 'list')],
            'domain': [('auto_discount_id', '=', self.id)],
            'context': {'create': False},
        }
