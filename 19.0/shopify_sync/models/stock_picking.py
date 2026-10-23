from odoo import _, models

from . import queries
from .shopify_instance import ShopifyError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        result = super()._action_done()
        for picking in self.filtered(lambda p: p.picking_type_code == 'outgoing' and p.sale_id.shopify_order_id):
            picking._shopify_export_fulfillment()
        return result

    def _shopify_export_fulfillment(self):
        """Mark the Shopify order as fulfilled, with the tracking number when there is one."""
        order = self.sale_id
        instance = order.shopify_instance_id
        try:
            fulfillment_orders = instance._graphql(
                queries.FULFILLMENT_ORDERS, {'id': order.shopify_order_id})['order']['fulfillmentOrders']['nodes']
            open_orders = [fo['id'] for fo in fulfillment_orders if fo['status'] in ('OPEN', 'IN_PROGRESS')]
            if not open_orders:
                return
            fulfillment = {
                'lineItemsByFulfillmentOrder': [{'fulfillmentOrderId': fo_id} for fo_id in open_orders],
                'notifyCustomer': True,
            }
            tracking = getattr(self, 'carrier_tracking_ref', False)
            if tracking:
                fulfillment['trackingInfo'] = {'number': tracking}
            result = instance._graphql(queries.FULFILLMENT_CREATE, {'fulfillment': fulfillment})['fulfillmentCreate']
            instance._user_errors(result, 'fulfillmentCreate')
            order.shopify_fulfillment_status = 'FULFILLED'
            instance._log('export_fulfillment', _("Fulfillment sent for %s", order.shopify_order_name),
                          res_model='stock.picking', res_id=self.id)
        except ShopifyError as e:
            instance._log('export_fulfillment', str(e), level='error', res_model='stock.picking', res_id=self.id)
