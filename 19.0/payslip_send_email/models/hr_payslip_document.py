import base64
import io
import re
import unicodedata

from babel.dates import format_date

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import get_lang
from odoo.tools.pdf import PdfFileReader, PdfFileWriter


def normalize_words(text):
    """ 'Payslip_JANSSENS-Lotte (2026-10).pdf' -> ['payslip', 'janssens', 'lotte', '2026', '10', 'pdf'] """
    text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode().lower()
    return [w for w in re.split(r'[^a-z0-9]+', text) if w]


class HrPayslipDocument(models.Model):
    _name = 'hr.payslip.document'
    _description = 'Payslip document'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_from desc, employee_name, id'

    name = fields.Char(compute='_compute_name', store=True, readonly=False, precompute=True)
    employee_id = fields.Many2one('hr.employee', 'Employee', tracking=True, index=True,
                                  domain="[('company_id', 'in', [company_id, False])]")
    employee_name = fields.Char(related='employee_id.name', store=True, string='Employee name')
    user_id = fields.Many2one(related='employee_id.user_id', store=True, string='User')
    department_id = fields.Many2one(related='employee_id.department_id', store=True, string='Department')
    batch_id = fields.Many2one('hr.payslip.document.batch', 'Batch', ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    date_from = fields.Date('From', required=True)
    date_to = fields.Date('To', required=True)
    period_label = fields.Char('Period', compute='_compute_period_label')
    pdf_file = fields.Binary('Payslip (PDF)', attachment=True, required=True)
    pdf_filename = fields.Char('File name')
    state = fields.Selection([
        ('draft', 'To send'),
        ('sent', 'Sent'),
        ('error', 'Not sent'),
        ('cancel', 'Cancelled'),
    ], default='draft', required=True, tracking=True, index=True)
    error_message = fields.Char('Reason', readonly=True)
    sent_date = fields.Datetime('Sent on', readonly=True, copy=False)
    sent_to = fields.Char('Sent to', readonly=True, copy=False)
    note = fields.Text()
    pdf_protected = fields.Boolean(compute='_compute_pdf_protected')

    _check_dates = models.Constraint('CHECK(date_from <= date_to)', 'The period must start before it ends.')

    @api.depends('company_id.payslip_pdf_password')
    def _compute_pdf_protected(self):
        for doc in self:
            doc.pdf_protected = doc.company_id.payslip_pdf_password != 'none'

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_name(self):
        for doc in self:
            doc.name = ' - '.join(filter(None, [doc.env._('Payslip %s', doc.period_label or ''),
                                                doc.employee_id.name]))

    @api.depends('date_from', 'date_to')
    def _compute_period_label(self):
        lang = get_lang(self.env).code
        for doc in self:
            if not doc.date_from or not doc.date_to:
                doc.period_label = ''
            elif (doc.date_from.day == 1 and doc.date_from.month == doc.date_to.month
                  and doc.date_from.year == doc.date_to.year):
                doc.period_label = format_date(doc.date_from, 'MMMM y', locale=lang).capitalize()
            else:
                doc.period_label = '%s - %s' % (format_date(doc.date_from, 'd MMM y', locale=lang),
                                                format_date(doc.date_to, 'd MMM y', locale=lang))

    # ------------------------------------------------------------------ matching

    @api.model
    def _match_employee(self, filename, employees):
        """ Find the employee a file belongs to: badge ID, or all words of the name in the file name
        ("Janssens_Lotte.pdf"), else all words of the name glued in the file name ("DeVries_Jan.pdf"). """
        words = set(normalize_words(filename))
        compact = ''.join(normalize_words(filename))
        exact = glued = self.env['hr.employee']
        for employee in employees.sudo():
            badge = (employee.barcode or '').lower()
            name_words = normalize_words(employee.name)
            if (badge and badge in words) or (name_words and set(name_words) <= words):
                exact |= employee
            elif name_words and all(word in compact for word in name_words):
                glued |= employee
        for found in (exact, glued):
            if found:
                return found if len(found) == 1 else self.env['hr.employee']
        return self.env['hr.employee']

    # ------------------------------------------------------------------ sending

    def _pdf_password(self):
        self.ensure_one()
        if self.company_id.payslip_pdf_password == 'birthday':
            birthday = self.employee_id.sudo().birthday
            if not birthday:
                return False
            return birthday.strftime('%d%m%Y')
        return None

    def _pdf_for_mail(self):
        """ The PDF to attach, protected with the employee's password when the company asks for it. """
        self.ensure_one()
        data = base64.b64decode(self.pdf_file)
        password = self._pdf_password()
        if password:
            reader = PdfFileReader(io.BytesIO(data), strict=False)
            writer = PdfFileWriter()
            for page in reader.pages:
                writer.add_page(page)
            writer.encrypt(password)
            out = io.BytesIO()
            writer.write(out)
            data = out.getvalue()
        return data

    def _check_sendable(self):
        self.ensure_one()
        if not self.employee_id:
            return self.env._('No employee: assign the payslip to an employee.')
        if self.employee_id.sudo().payslip_email_mode == 'none':
            return self.env._('The employee receives payslips by hand.')
        if not self.employee_id._payslip_email_addresses():
            return self.env._('No e-mail address for this employee.')
        if self.company_id.payslip_pdf_password == 'birthday' and self._pdf_password() is False:
            return self.env._('No date of birth to protect the PDF.')
        return False

    def _send(self):
        template = self.env.ref('payslip_send_email.mail_template_payslip')
        for doc in self:
            if doc.state not in ('draft', 'error'):
                continue
            error = doc._check_sendable()
            if error:
                doc.write({'state': 'error', 'error_message': error})
                continue
            emails = doc.employee_id._payslip_email_addresses()
            attachment = self.env['ir.attachment'].sudo().create({
                'name': doc.pdf_filename or ('%s.pdf' % doc.name),
                'datas': base64.b64encode(doc._pdf_for_mail()),
                'mimetype': 'application/pdf',
            })
            template.send_mail(
                doc.id,
                email_layout_xmlid='mail.mail_notification_light',
                email_values={'email_to': ','.join(emails), 'recipient_ids': [],
                              'attachment_ids': [(4, attachment.id)]},
            )
            doc.write({'state': 'sent', 'sent_date': fields.Datetime.now(), 'sent_to': ', '.join(emails),
                       'error_message': False})
            doc.message_post(body=self.env._('Payslip e-mailed to %s.', ', '.join(emails)),
                             subtype_xmlid='mail.mt_note')
        return True

    def action_send(self):
        if any(doc.state == 'cancel' for doc in self):
            raise UserError(self.env._('Cancelled payslips cannot be sent.'))
        self.filtered(lambda d: d.state in ('draft', 'error'))._send()
        sent = self.filtered(lambda d: d.state == 'sent')
        failed = self.filtered(lambda d: d.state == 'error')
        message = self.env._('%(sent)s payslip(s) sent.', sent=len(sent))
        if failed:
            message += ' ' + self.env._('%(failed)s not sent, see the reason on each payslip.', failed=len(failed))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'warning' if failed else 'success', 'message': message,
                           'next': {'type': 'ir.actions.act_window_close'}}}

    def action_resend(self):
        self.filtered(lambda d: d.state == 'sent').write({'state': 'draft'})
        return self.action_send()

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reset(self):
        self.write({'state': 'draft', 'error_message': False})

    def action_download(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/hr.payslip.document/{self.id}/pdf_file/{self.pdf_filename or "payslip.pdf"}'
                   '?download=true',
            'target': 'self',
        }
