from odoo import _, fields, models

from .shopify_instance import FINANCIAL_STATUSES


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    shopify_instance_id = fields.Many2one('shopify.instance', string="Shopify store", readonly=True,
                                          index='btree_not_null', copy=False)
    shopify_order_id = fields.Char("Shopify order ID", readonly=True, copy=False)
    shopify_order_name = fields.Char("Shopify order", readonly=True, copy=False)
    shopify_financial_status = fields.Selection(FINANCIAL_STATUSES, readonly=True, copy=False)
    shopify_fulfillment_status = fields.Char(readonly=True, copy=False)

    _shopify_order_uniq = models.Constraint('UNIQUE(shopify_instance_id, shopify_order_id)',
                                            "This Shopify order was already imported.")

    def _shopify_update_status(self, data):
        self.ensure_one()
        self.write({
            'shopify_financial_status': data.get('displayFinancialStatus') or self.shopify_financial_status,
            'shopify_fulfillment_status': data.get('displayFulfillmentStatus') or self.shopify_fulfillment_status,
        })
        if data.get('cancelledAt') and self.state != 'cancel':
            if any(p.state == 'done' for p in self.picking_ids) or self.invoice_ids.filtered(lambda i: i.state == 'posted'):
                self.activity_schedule('mail.mail_activity_data_todo', summary=_("Cancelled in Shopify"),
                                       note=_("Order %s was cancelled in Shopify but is already delivered or "
                                              "invoiced: cancel it manually.", self.shopify_order_name),
                                       user_id=self.user_id.id or self.env.uid)
            else:
                self._action_cancel()
                self.shopify_instance_id._log('import_order', _("Order %s cancelled from Shopify.", self.name),
                                              res_model=self._name, res_id=self.id)
