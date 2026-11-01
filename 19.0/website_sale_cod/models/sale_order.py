import secrets

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    cod_collection_ids = fields.One2many('sale.cod.collection', 'order_id', string='COD collections')
    cod_collection_count = fields.Integer(compute='_compute_cod_collection_count')
    cod_otp = fields.Char('Delivery code', copy=False, readonly=True,
                          groups='sales_team.group_sale_salesman')
    cod_state = fields.Selection(related='cod_collection_ids.state', string='COD status')
    is_cod = fields.Boolean('Cash on delivery', compute='_compute_is_cod', search='_search_is_cod')

    def _compute_cod_collection_count(self):
        counts = dict(self.env['sale.cod.collection']._read_group(
            [('order_id', 'in', self.ids)], ['order_id'], ['__count']))
        for order in self:
            order.cod_collection_count = counts.get(order, 0)

    @api.depends('transaction_ids.provider_id.custom_mode')
    def _compute_is_cod(self):
        for order in self:
            order.is_cod = any(tx.provider_id.custom_mode == 'cash_on_delivery'
                               for tx in order.sudo().transaction_ids)

    def _search_is_cod(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        cod_ids = self.sudo().search([('transaction_ids.provider_id.custom_mode', '=', 'cash_on_delivery')]).ids
        return [('id', 'in' if (operator == '=') == value else 'not in', cod_ids)]

    def _cod_new_otp(self, length=6):
        length = min(max(length or 6, 4), 10)
        return ''.join(secrets.choice('0123456789') for _i in range(length))

    def _cod_start(self, tx):
        """Create the collection receipt of a confirmed cash on delivery order and send the code."""
        self.ensure_one()
        provider = tx.provider_id
        order = self.sudo()
        if provider.cod_otp and not order.cod_otp:
            order.cod_otp = self._cod_new_otp(provider.cod_otp_length)
        collection = self.env['sale.cod.collection'].sudo().create({
            'order_id': order.id, 'transaction_id': tx.id, 'amount_due': order.amount_total,
        })
        if provider.cod_otp:
            template = self.env.ref('website_sale_cod.mail_template_cod_code', raise_if_not_found=False)
            if template:
                order.with_context(mail_notify_force_send=False).message_post_with_source(
                    template, subtype_xmlid='mail.mt_comment', email_layout_xmlid='mail.mail_notification_light')
        return collection

    def action_view_cod_collections(self):
        action = self.env['ir.actions.act_window']._for_xml_id('website_sale_cod.action_sale_cod_collection')
        action['domain'] = [('order_id', 'in', self.ids)]
        if len(self.cod_collection_ids) == 1:
            action.update(view_mode='form', views=[(False, 'form')], res_id=self.cod_collection_ids.id)
        return action

    def action_cod_regenerate_code(self):
        for order in self.sudo().filtered('cod_otp'):
            provider = order.cod_collection_ids[:1].transaction_id.provider_id
            order.cod_otp = self._cod_new_otp(provider.cod_otp_length if provider else 6)
            template = self.env.ref('website_sale_cod.mail_template_cod_code', raise_if_not_found=False)
            if template:
                order.message_post_with_source(template, subtype_xmlid='mail.mt_comment',
                                               email_layout_xmlid='mail.mail_notification_light')
        return True
