from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import consteq

MAX_ATTEMPTS = 5


class SaleCodCollection(models.Model):
    _name = 'sale.cod.collection'
    _description = 'Cash on delivery collection'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char('Reference', required=True, readonly=True, copy=False, default='/')
    order_id = fields.Many2one('sale.order', required=True, readonly=True, index=True, ondelete='cascade')
    transaction_id = fields.Many2one('payment.transaction', readonly=True)
    order_ref = fields.Char('Order reference', related='order_id.name', store=True)
    partner_id = fields.Many2one(related='order_id.partner_id', store=True)
    customer_name = fields.Char('Deliver to', related='order_id.partner_shipping_id.name')
    customer_phone = fields.Char('Phone', compute='_compute_delivery_info')
    delivery_address = fields.Text(compute='_compute_delivery_info')
    company_id = fields.Many2one(related='order_id.company_id', store=True)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True)
    amount_due = fields.Monetary('Amount to collect', readonly=True, tracking=True)
    amount_collected = fields.Monetary(readonly=True, tracking=True)
    state = fields.Selection([('draft', 'To collect'), ('collected', 'Collected'), ('done', 'Deposited'),
                              ('cancel', 'Cancelled')], default='draft', required=True, readonly=True,
                             tracking=True, index=True, group_expand=True)
    driver_id = fields.Many2one('res.users', 'Delivery person', tracking=True,
                                domain=[('share', '=', False)])
    date_collected = fields.Datetime('Collected on', readonly=True)
    date_deposited = fields.Datetime('Deposited on', readonly=True)
    otp_attempts = fields.Integer('Wrong codes', readonly=True)
    cancel_reason = fields.Text(readonly=True)
    payment_id = fields.Many2one('account.payment', readonly=True)
    invoice_ids = fields.Many2many(related='order_id.invoice_ids', string='Invoices')
    note = fields.Text()

    @api.depends('order_id.partner_shipping_id')
    def _compute_delivery_info(self):
        for collection in self:
            partner = collection.order_id.sudo().partner_shipping_id
            collection.customer_phone = partner.phone or collection.order_id.sudo().partner_id.phone or False
            collection.delivery_address = partner._display_address() if partner else False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].sudo().next_by_code('sale.cod.collection') or '/'
        return super().create(vals_list)

    @api.depends('name', 'order_id')
    def _compute_display_name(self):
        for collection in self:
            collection.display_name = f'{collection.name} ({collection.order_ref})' \
                if collection.order_ref else collection.name

    # ------------------------------------------------------------------
    # collect (delivery person)
    # ------------------------------------------------------------------
    def _cod_code_required(self):
        """A code is asked when the order has one and the provider (if any) uses codes."""
        self.ensure_one()
        collection = self.sudo()
        provider = collection.transaction_id.provider_id
        return bool(collection.order_id.cod_otp and (not provider or provider.cod_otp))

    def _cod_check_code(self, code):
        self.ensure_one()
        if not self._cod_code_required():
            return True
        expected = self.sudo().order_id.cod_otp
        if self.otp_attempts >= MAX_ATTEMPTS:
            raise UserError(self.env._('Too many wrong codes for %s. A manager must send a new code to the '
                                       'customer.', self.order_id.name))
        if not consteq((code or '').strip(), expected):
            self.sudo().otp_attempts += 1
            self.sudo().message_post(body=self.env._('Wrong delivery code entered by %s.', self.env.user.name))
            return False
        return True

    def _cod_collect(self, code, amount, driver=None, note=None, code_checked=False):
        """Confirm that the cash was collected at the door."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(self.env._('%s is not waiting for a collection.', self.name))
        if not code_checked and not self._cod_check_code(code):
            raise UserError(self.env._('The delivery code is not correct.'))
        if self.currency_id.compare_amounts(amount, self.amount_due) != 0:
            raise UserError(self.env._(
                'The collected amount (%(collected)s) differs from the amount due (%(due)s). Collect the exact '
                'amount or cancel the collection with a reason.',
                collected=self.currency_id.format(amount), due=self.currency_id.format(self.amount_due)))
        self.write({'state': 'collected', 'amount_collected': amount, 'date_collected': fields.Datetime.now(),
                    'driver_id': (driver or self.env.user).id, 'note': note or self.note})
        self.message_post(body=self.env._('Cash collected: %s.', self.currency_id.format(amount)))
        return True

    # ------------------------------------------------------------------
    # deposit (company)
    # ------------------------------------------------------------------
    def action_deposit(self):
        if not self.env.user.has_group('sales_team.group_sale_manager') and not self.env.su:
            raise UserError(self.env._('Only sales managers can register the deposit of cash.'))
        for collection in self:
            if collection.state != 'collected':
                raise UserError(self.env._('%s has not been collected yet.', collection.name))
            collection.sudo()._cod_deposit()
        return True

    def _cod_deposit(self):
        self.ensure_one()
        order, tx = self.order_id, self.transaction_id
        provider = tx.provider_id
        payment = self.env['account.payment']
        if provider.cod_invoice_on_deposit:
            invoices = order.invoice_ids.filtered(lambda m: m.state != 'cancel' and m.move_type == 'out_invoice')
            if not invoices:
                invoices = order._create_invoices(final=True)
            invoices.filtered(lambda m: m.state == 'draft').action_post()
            open_invoices = invoices.filtered(lambda m: m.payment_state not in ('paid', 'in_payment', 'reversed'))
            journal = provider.cod_journal_id or self.env['account.journal'].search(
                [('type', '=', 'cash'), ('company_id', '=', self.company_id.id)], limit=1)
            if open_invoices and not journal:
                raise UserError(self.env._('Set a cash journal on the Cash on Delivery payment provider.'))
            if open_invoices:
                wizard = self.env['account.payment.register'].with_context(
                    active_model='account.move', active_ids=open_invoices.ids).create({
                        'journal_id': journal.id,
                        'amount': self.amount_collected,
                        'payment_date': fields.Date.context_today(self),
                        'communication': f'{order.name} - {self.name}',
                    })
                payment = wizard._create_payments()
        if tx:
            # the cash is in: close the transaction ourselves (Odoo must not create a second payment)
            tx = tx.with_context(payment_safe_write=True)
            if tx.state == 'pending':
                tx._set_done()
            tx.write({'is_post_processed': True, 'payment_id': payment[:1].id or tx.payment_id.id})
        self.write({'state': 'done', 'date_deposited': fields.Datetime.now(), 'payment_id': payment[:1].id})
        self.message_post(body=self.env._('Cash deposited at the company.'))

    def action_cancel_wizard(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': 'sale.cod.cancel.wizard', 'view_mode': 'form',
            'target': 'new', 'name': self.env._('Cancel collection'),
            'context': {'default_collection_ids': self.ids},
        }

    def _cod_cancel(self, reason):
        for collection in self:
            if collection.state == 'done':
                raise UserError(self.env._('%s was already deposited.', collection.name))
            collection.write({'state': 'cancel', 'cancel_reason': reason})
            collection.message_post(body=self.env._('Collection cancelled: %s', reason))
            if collection.transaction_id.state == 'pending':
                collection.transaction_id.sudo().with_context(payment_safe_write=True)._set_canceled(
                    state_message=reason)

    def action_reset(self):
        self.filtered(lambda c: c.state == 'cancel').write({'state': 'draft', 'cancel_reason': False,
                                                            'otp_attempts': 0})

    def action_collect_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'sale.cod.collect.wizard', 'view_mode': 'form',
            'target': 'new', 'name': self.env._('Collect %s', self.name),
            'context': {'default_collection_id': self.id},
        }

    def action_new_code(self):
        self.order_id.action_cod_regenerate_code()
        self.sudo().otp_attempts = 0
        self.message_post(body=self.env._('A new delivery code was sent to the customer.'))
        return True

    def action_view_order(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'sale.order', 'res_id': self.order_id.id,
                'view_mode': 'form', 'views': [(False, 'form')]}
