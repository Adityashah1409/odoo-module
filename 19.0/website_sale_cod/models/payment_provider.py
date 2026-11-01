from odoo import _, api, fields, models

from odoo.addons.payment import utils as payment_utils


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    cod_min_amount = fields.Monetary('Minimum order amount', currency_field='main_currency_id',
                                     help='Cash on delivery is offered from this order total. 0 = no minimum.')
    cod_excluded_categ_ids = fields.Many2many(
        'product.category', 'payment_provider_cod_categ_rel', 'provider_id', 'categ_id',
        string='Excluded product categories',
        help='Cash on delivery is not offered when the cart contains a product of these categories '
             '(e.g. made-to-order or digital goods).')
    cod_otp = fields.Boolean('Delivery code (OTP)', default=True,
                             help='The customer receives a code to give to the driver; the collection is only '
                                  'confirmed with the right code.')
    cod_otp_length = fields.Integer('Code length', default=6)
    cod_journal_id = fields.Many2one('account.journal', 'Cash journal',
                                     domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
                                     help='Journal of the payments registered when the cash is deposited.')
    cod_invoice_on_deposit = fields.Boolean('Invoice when deposited', default=True,
                                            help='Create, post and pay the invoice when the cash reaches the '
                                                 'company.')

    @api.model
    def _get_compatible_providers(self, *args, sale_order_id=None, report=None, **kwargs):
        providers = super()._get_compatible_providers(*args, sale_order_id=sale_order_id, report=report,
                                                      **kwargs)
        return self._cod_filter(providers, sale_order_id, report)

    @api.model
    def _cod_filter(self, providers, sale_order_id, report):
        """Remove the cash on delivery providers whose rules the order does not meet."""
        order = self.env['sale.order'].browse(sale_order_id).exists() if sale_order_id else None
        if not order:
            return providers
        result = providers
        for provider in providers.filtered(lambda p: p.custom_mode == 'cash_on_delivery'):
            reason = provider._cod_unavailable_reason(order)
            if reason:
                result -= provider
                payment_utils.add_to_report(report, provider, available=False, reason=reason)
        return result

    def _cod_unavailable_reason(self, order):
        self.ensure_one()
        if self.cod_min_amount and order.currency_id.compare_amounts(
                order.amount_total, order.currency_id._convert(self.cod_min_amount, order.currency_id,
                                                               order.company_id, fields.Date.today())) < 0:
            return _('order below the minimum amount for cash on delivery')
        if self.cod_excluded_categ_ids:
            categories = order.order_line.product_id.categ_id
            if categories and self.env['product.category'].search(
                    [('id', 'parent_of', categories.ids)]) & self.cod_excluded_categ_ids:
                return _('the cart contains products that cannot be paid at delivery')
        return False
