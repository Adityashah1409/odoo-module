from odoo import models


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _post_process(self):
        """After Odoo confirmed the cash on delivery orders: delivery code and collection receipt."""
        cod_txs = self.filtered(lambda tx: tx.provider_id.custom_mode == 'cash_on_delivery' and tx.state == 'pending')
        super()._post_process()
        for tx in cod_txs:
            for order in tx.sale_order_ids.filtered(lambda so: so.state == 'sale' and not so.cod_collection_ids):
                order._cod_start(tx)
