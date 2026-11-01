from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrPayslipDocumentBatch(models.Model):
    _name = 'hr.payslip.document.batch'
    _description = 'Payslip batch'
    _inherit = ['mail.thread']
    _order = 'date_from desc, id desc'

    def _default_date_from(self):
        return fields.Date.today().replace(day=1) - relativedelta(months=1)

    def _default_date_to(self):
        return fields.Date.today().replace(day=1) - relativedelta(days=1)

    name = fields.Char(compute='_compute_name', store=True, readonly=False, required=True, precompute=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date_from = fields.Date('From', required=True, default=_default_date_from)
    date_to = fields.Date('To', required=True, default=_default_date_to)
    document_ids = fields.One2many('hr.payslip.document', 'batch_id', 'Payslips')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('done', 'Sent'),
    ], default='draft', required=True, tracking=True)
    scheduled_date = fields.Datetime('Send on', tracking=True)
    count_total = fields.Integer('Number of payslips', compute='_compute_counts')
    count_draft = fields.Integer('To send', compute='_compute_counts')
    count_sent = fields.Integer('Sent', compute='_compute_counts')
    count_error = fields.Integer('Not sent', compute='_compute_counts')
    count_unassigned = fields.Integer('Without employee', compute='_compute_counts')

    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for batch in self:
            label = self.env['hr.payslip.document'].new(
                {'date_from': batch.date_from, 'date_to': batch.date_to}).period_label
            batch.name = self.env._('Payslips %s', label) if label else self.env._('Payslips')

    @api.depends('document_ids.state', 'document_ids.employee_id')
    def _compute_counts(self):
        for batch in self:
            docs = batch.document_ids.filtered(lambda d: d.state != 'cancel')
            batch.count_total = len(docs)
            batch.count_draft = len(docs.filtered(lambda d: d.state == 'draft'))
            batch.count_sent = len(docs.filtered(lambda d: d.state == 'sent'))
            batch.count_error = len(docs.filtered(lambda d: d.state == 'error'))
            batch.count_unassigned = len(docs.filtered(lambda d: not d.employee_id))

    def write(self, vals):
        res = super().write(vals)
        if {'date_from', 'date_to'} & set(vals):
            for batch in self:
                batch.document_ids.filtered(lambda d: d.state == 'draft').write(
                    {'date_from': batch.date_from, 'date_to': batch.date_to})
        return res

    def action_open_import(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Import payslip PDFs'),
            'res_model': 'hr.payslip.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_batch_id': self.id},
        }

    def action_send_all(self):
        self.ensure_one()
        docs = self.document_ids.filtered(lambda d: d.state in ('draft', 'error'))
        if not docs:
            raise UserError(self.env._('There is nothing to send in %s.', self.name))
        action = docs.action_send()
        self._check_done()
        return action

    def _check_done(self):
        for batch in self:
            if batch.document_ids and not batch.document_ids.filtered(lambda d: d.state in ('draft', 'error')):
                batch.write({'state': 'done', 'scheduled_date': False})

    def action_schedule(self):
        for batch in self:
            if not batch.scheduled_date:
                raise UserError(self.env._('Set the date and time to send %s.', batch.name))
            if not batch.document_ids:
                raise UserError(self.env._('Import the payslips of %s first.', batch.name))
        self.write({'state': 'scheduled'})

    def action_unschedule(self):
        self.write({'state': 'draft'})

    def action_view_documents(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('payslip_send_email.action_payslip_document')
        action['domain'] = [('batch_id', '=', self.id)]
        action['context'] = {'default_batch_id': self.id}
        return action

    @api.model
    def _cron_send_scheduled(self):
        batches = self.search([('state', '=', 'scheduled'), ('scheduled_date', '<=', fields.Datetime.now())])
        for batch in batches:
            batch.document_ids.filtered(lambda d: d.state == 'draft')._send()
            batch.state = 'done'
            batch.message_post(body=self.env._(
                'Scheduled sending done: %(sent)s sent, %(error)s not sent.',
                sent=batch.count_sent, error=batch.count_error))
