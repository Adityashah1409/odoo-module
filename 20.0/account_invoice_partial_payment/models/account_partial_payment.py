from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import clean_context, float_compare, format_amount

INVOICE_TYPE = {'inbound': 'out_invoice', 'outbound': 'in_invoice'}


class AccountPartialPayment(models.Model):
    _name = 'account.partial.payment'
    _description = 'Partial Payment Batch'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(default='/', readonly=True, copy=False)
    state = fields.Selection([
        ('draft', 'Draft'), ('posted', 'Posted'), ('cancel', 'Cancelled'),
    ], default='draft', required=True, readonly=True, tracking=True, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    payment_type = fields.Selection([
        ('inbound', 'Customer receipt'), ('outbound', 'Vendor payment'),
    ], required=True, default='inbound')
    partner_id = fields.Many2one('res.partner', required=True, tracking=True,
                                 domain="[('parent_id', '=', False)]")
    journal_id = fields.Many2one(
        'account.journal', required=True, check_company=True, tracking=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        default=lambda self: self.env['account.journal'].search([
            ('type', '=', 'bank'), ('company_id', '=', self.env.company.id)], limit=1))
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id', store=True, readonly=False,
                                  required=True, precompute=True)
    date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    amount = fields.Monetary('Amount received / paid', tracking=True,
                             help='Total of the receipt or payment. What is not allocated stays as outstanding credit (or debit).')
    memo = fields.Char()
    line_ids = fields.One2many('account.partial.payment.line', 'batch_id', string='Allocations', copy=False)
    allocated_amount = fields.Monetary(compute='_compute_amounts', store=True)
    unallocated_amount = fields.Monetary(compute='_compute_amounts', store=True,
                                         help='Becomes an outstanding credit (customer) or debit (vendor) of the partner.')
    partner_outstanding = fields.Monetary(
        'Existing outstanding', compute='_compute_partner_outstanding',
        help='Open credit (customer) or debit (vendor) the partner already has, before this batch.')
    payment_ids = fields.One2many('account.payment', 'partial_batch_id', string='Payments', readonly=True)
    payment_count = fields.Integer(compute='_compute_counts')
    invoice_count = fields.Integer(compute='_compute_counts')

    _amount_positive = models.Constraint('CHECK(amount >= 0)', 'The amount cannot be negative.')

    @api.depends('journal_id', 'company_id')
    def _compute_currency_id(self):
        for batch in self:
            batch.currency_id = batch.journal_id.currency_id or batch.company_id.currency_id

    @api.depends('amount', 'line_ids.amount')
    def _compute_amounts(self):
        for batch in self:
            batch.allocated_amount = sum(batch.line_ids.mapped('amount'))
            batch.unallocated_amount = batch.amount - batch.allocated_amount

    @api.depends('partner_id', 'payment_type', 'company_id')
    def _compute_partner_outstanding(self):
        for batch in self:
            if not batch.partner_id:
                batch.partner_outstanding = 0.0
                continue
            lines = self.env['account.move.line'].search(batch._outstanding_domain())
            sign = -1 if batch.payment_type == 'inbound' else 1
            batch.partner_outstanding = sign * sum(lines.mapped('amount_residual'))

    @api.depends('payment_ids', 'line_ids.move_id')
    def _compute_counts(self):
        for batch in self:
            batch.payment_count = len(batch.payment_ids)
            batch.invoice_count = len(batch.line_ids.move_id)

    def _outstanding_domain(self):
        self.ensure_one()
        account_type = 'asset_receivable' if self.payment_type == 'inbound' else 'liability_payable'
        return [
            ('company_id', '=', self.company_id.id),
            ('partner_id', 'child_of', self.partner_id.commercial_partner_id.id),
            ('account_id.account_type', '=', account_type),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('amount_residual', '<' if self.payment_type == 'inbound' else '>', 0),
        ]

    def _open_invoice_domain(self):
        self.ensure_one()
        return [
            ('company_id', '=', self.company_id.id),
            ('commercial_partner_id', '=', self.partner_id.commercial_partner_id.id),
            ('move_type', '=', INVOICE_TYPE[self.payment_type]),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('currency_id', '=', self.currency_id.id),
        ]

    # ------------------------------------------------------------------ actions
    def action_load_invoices(self):
        """Add every open invoice/bill of the partner (oldest due first) with nothing allocated yet."""
        for batch in self:
            batch._check_draft()
            present = batch.line_ids.move_id
            moves = self.env['account.move'].search(batch._open_invoice_domain(), order='invoice_date_due, id')
            batch.line_ids = [(0, 0, {'move_id': move.id, 'amount': 0.0}) for move in moves - present]

    def action_auto_allocate(self):
        """Spread the amount over the lines, oldest due date first."""
        for batch in self:
            batch._check_draft()
            if not batch.line_ids:
                batch.action_load_invoices()
            remaining = batch.amount
            for line in batch.line_ids.sorted(lambda l: (l.date_due or fields.Date.today(), l.id)):
                line.amount = min(line.amount_residual, max(remaining, 0.0))
                remaining -= line.amount

    def action_post(self):
        # default_* keys (e.g. from the invoice button) must not reach the payments
        self = self.with_context(clean_context(self.env.context))
        for batch in self:
            batch._check_draft()
            batch._check_allocations()
            batch.line_ids.filtered(lambda l: batch.currency_id.is_zero(l.amount)).unlink()
            if batch.name == '/':
                batch.name = self.env['ir.sequence'].with_company(batch.company_id).next_by_code('account.partial.payment') or '/'
            memo = batch.memo or batch.name
            payments = self.env['account.payment']
            for line in batch.line_ids:
                wizard = self.env['account.payment.register'].with_context(
                    active_model='account.move', active_ids=line.move_id.ids,
                ).create({
                    'payment_date': batch.date,
                    'journal_id': batch.journal_id.id,
                    'currency_id': batch.currency_id.id,
                    'amount': line.amount,
                    'communication': f'{memo} - {line.move_id.name}',
                })
                wizard.payment_difference_handling = 'open'
                line_payments = wizard._create_payments()
                line.payment_id = line_payments[:1]
                payments |= line_payments
            if not batch.currency_id.is_zero(batch.unallocated_amount):
                rest = self.env['account.payment'].create({
                    'payment_type': batch.payment_type,
                    'partner_type': 'customer' if batch.payment_type == 'inbound' else 'supplier',
                    'partner_id': batch.partner_id.commercial_partner_id.id,
                    'amount': batch.unallocated_amount,
                    'currency_id': batch.currency_id.id,
                    'journal_id': batch.journal_id.id,
                    'date': batch.date,
                    'memo': f'{memo} - unallocated',
                })
                rest.action_post()
                payments |= rest
            payments.partial_batch_id = batch
            batch.state = 'posted'
            batch.message_post(body=self.env._(
                'Posted: %(count)s payment(s), %(allocated)s allocated, %(rest)s left as outstanding.',
                count=len(payments), allocated=format_amount(self.env, batch.allocated_amount, batch.currency_id),
                rest=format_amount(self.env, batch.unallocated_amount, batch.currency_id)))
        return True

    def action_cancel(self):
        """Cancel the payments: invoices get their residual back."""
        for batch in self:
            if batch.state != 'posted':
                raise UserError(self.env._('Only posted batches can be cancelled.'))
            for payment in batch.payment_ids:
                if payment.state not in ('draft', 'canceled'):
                    payment.action_draft()
                payment.action_cancel()
            batch.state = 'cancel'

    def action_draft(self):
        for batch in self:
            if batch.state != 'cancel':
                raise UserError(self.env._('Only cancelled batches can be reset to draft.'))
            batch.payment_ids.partial_batch_id = False
            batch.line_ids.payment_id = False
            batch.state = 'draft'

    def action_view_payments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Payments'),
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('partial_batch_id', '=', self.id)],
            'context': {'create': False},
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.line_ids.move_id.ids)],
            'context': {'create': False},
        }

    # ------------------------------------------------------------------ checks
    def _check_draft(self):
        if self.state != 'draft':
            raise UserError(self.env._('%s is not a draft.', self.name))

    def _check_allocations(self):
        self.ensure_one()
        currency = self.currency_id
        if currency.is_zero(self.amount):
            raise ValidationError(self.env._('Enter the amount received or paid.'))
        if float_compare(self.allocated_amount, self.amount, precision_rounding=currency.rounding) > 0:
            raise ValidationError(self.env._(
                'You allocate %(allocated)s but the payment is only %(amount)s.',
                allocated=self.allocated_amount, amount=self.amount))
        partner = self.partner_id.commercial_partner_id
        for line in self.line_ids:
            move = line.move_id
            if move.commercial_partner_id != partner or move.move_type != INVOICE_TYPE[self.payment_type]:
                raise ValidationError(self.env._('%s does not belong to this partner and payment type.', move.display_name))
            if move.state != 'posted' or move.payment_state not in ('not_paid', 'partial'):
                raise ValidationError(self.env._('%s is not open.', move.display_name))
            if move.currency_id != currency:
                raise ValidationError(self.env._('%s is not in %s.', move.display_name, currency.name))
            if float_compare(line.amount, 0.0, precision_rounding=currency.rounding) < 0:
                raise ValidationError(self.env._('Negative amount on %s.', move.display_name))
            if float_compare(line.amount, move.amount_residual, precision_rounding=currency.rounding) > 0:
                raise ValidationError(self.env._(
                    '%(move)s: %(amount)s is more than the amount due (%(due)s).',
                    move=move.display_name, amount=line.amount, due=move.amount_residual))
        if len(self.line_ids.move_id) != len(self.line_ids):
            raise ValidationError(self.env._('An invoice appears twice.'))

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if any(batch.state == 'posted' for batch in self):
            raise UserError(self.env._('Cancel a posted batch before deleting it.'))


class AccountPartialPaymentLine(models.Model):
    _name = 'account.partial.payment.line'
    _description = 'Partial Payment Allocation'
    _order = 'date_due, id'

    batch_id = fields.Many2one('account.partial.payment', required=True, ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='batch_id.currency_id')
    move_id = fields.Many2one('account.move', string='Invoice', required=True, ondelete='restrict')
    invoice_date = fields.Date(related='move_id.invoice_date')
    date_due = fields.Date(related='move_id.invoice_date_due', store=True)
    amount_total = fields.Monetary(related='move_id.amount_total', string='Total')
    amount_residual = fields.Monetary(compute='_compute_amount_residual', string='Amount due')
    amount = fields.Monetary('To pay')
    remaining = fields.Monetary(compute='_compute_remaining', string='Left to pay')
    payment_id = fields.Many2one('account.payment', readonly=True, copy=False)

    @api.depends('move_id.amount_residual', 'amount', 'batch_id.state')
    def _compute_amount_residual(self):
        for line in self:
            residual = line.move_id.amount_residual
            # once posted, show the amount that was due before this batch
            if line.batch_id.state == 'posted' and line.payment_id:
                residual += line.amount
            line.amount_residual = residual

    @api.depends('amount_residual', 'amount')
    def _compute_remaining(self):
        for line in self:
            line.remaining = line.amount_residual - line.amount

    @api.onchange('move_id')
    def _onchange_move_id(self):
        if self.move_id and not self.amount:
            self.amount = self.move_id.amount_residual
