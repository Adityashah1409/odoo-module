from odoo import api, fields, models


class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    # set by the register (plain integer: the rule model is not loaded in the POS data layer)
    auto_discount_ref = fields.Integer('Automatic discount rule ID', copy=False)
    auto_discount_id = fields.Many2one(
        'pos.auto.discount', string='Automatic discount', compute='_compute_auto_discount_id',
        store=True, index='btree_not_null', ondelete='set null')
    auto_discount_amount = fields.Monetary(
        'Automatic discount amount', compute='_compute_auto_discount_amount', store=True,
        currency_field='currency_id', help='Amount (tax included) saved thanks to the automatic discount.')

    @api.depends('auto_discount_ref')
    def _compute_auto_discount_id(self):
        refs = set(self.mapped('auto_discount_ref')) - {0}
        existing = set(self.env['pos.auto.discount'].with_context(active_test=False).browse(refs).exists().ids)
        for line in self:
            line.auto_discount_id = line.auto_discount_ref if line.auto_discount_ref in existing else False

    @api.depends('auto_discount_id', 'discount', 'price_subtotal_incl', 'price_unit', 'qty')
    def _compute_auto_discount_amount(self):
        for line in self:
            if not line.auto_discount_id or not line.discount:
                line.auto_discount_amount = 0.0
            elif line.discount >= 100:
                line.auto_discount_amount = line.price_unit * line.qty
            else:
                line.auto_discount_amount = line.price_subtotal_incl * line.discount / (100 - line.discount)

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        return fields_list + ['auto_discount_ref'] if fields_list else fields_list
