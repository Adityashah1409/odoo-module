from odoo import api, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _order_notification_channel(self):
        """ 'website' for eCommerce orders (website_sale installed), else 'backend'. """
        self.ensure_one()
        return 'website' if 'website_id' in self._fields and self.website_id else 'backend'

    def _notify_order_rules(self, trigger):
        if self.env.context.get('skip_order_notification'):
            return
        rules = self.env['sale.order.notification.rule'].sudo().search([('trigger', '=', trigger)])
        if not rules:
            return
        for order in self:
            for rule in rules:
                if rule._matches(order):
                    rule._send(order)

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        # eCommerce carts are created long before they are orders: only backend quotations here
        orders.filtered(lambda o: o.state == 'draft' and o._order_notification_channel() == 'backend')\
            ._notify_order_rules('create')
        return orders

    def action_confirm(self):
        to_notify = self.filtered(lambda o: o.state in ('draft', 'sent'))
        res = super().action_confirm()
        to_notify.filtered(lambda o: o.state == 'sale')._notify_order_rules('confirm')
        return res

    def _action_cancel(self):
        to_notify = self.filtered(lambda o: o.state != 'cancel')
        res = super()._action_cancel()
        to_notify.filtered(lambda o: o.state == 'cancel')._notify_order_rules('cancel')
        return res
