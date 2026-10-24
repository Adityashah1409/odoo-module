from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cpq_configuration_ids = fields.One2many('cpq.configuration', 'order_id')
    cpq_configuration_count = fields.Integer(compute='_compute_cpq_counts')
    cpq_production_count = fields.Integer(compute='_compute_cpq_counts')

    def _compute_cpq_counts(self):
        for order in self:
            order.cpq_configuration_count = len(order.cpq_configuration_ids)
            order.cpq_production_count = len(order.cpq_configuration_ids.production_ids)

    def action_cpq_configure(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'cpq.configure.wizard', 'view_mode': 'form',
            'target': 'new', 'name': self.env._("Configure a product"),
            'context': {'default_order_id': self.id},
        }

    def action_view_cpq_configurations(self):
        action = self.env['ir.actions.act_window']._for_xml_id('sale_cpq_configurator.action_cpq_configuration')
        action['domain'] = [('order_id', '=', self.id)]
        return action

    def action_view_cpq_productions(self):
        return self.cpq_configuration_ids.action_view_productions()

    def action_confirm(self):
        result = super().action_confirm()
        configurations = self.cpq_configuration_ids.filtered(lambda c: c.sale_line_id and c.state == 'quote')
        configurations._create_productions()
        return result

    def _action_cancel(self):
        result = super()._action_cancel()
        self.cpq_configuration_ids.filtered(lambda c: c.state == 'quote').write({'state': 'cancel'})
        return result


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    cpq_configuration_id = fields.Many2one('cpq.configuration', readonly=True, copy=False, index='btree_not_null')

    def _compute_price_unit(self):
        # configured lines keep the price computed by the configurator
        configured = self.filtered('cpq_configuration_id')
        super(SaleOrderLine, self - configured)._compute_price_unit()
