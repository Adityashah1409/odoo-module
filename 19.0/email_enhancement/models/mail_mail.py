from odoo import api, fields, models
from odoo.tools.mail import email_normalize_all


class MailMail(models.Model):
    _inherit = 'mail.mail'

    email_bcc = fields.Char('Bcc', help='Hidden copies: these addresses receive the e-mail without appearing in it.')

    def _send(self, *args, **kwargs):
        bcc_map = {mail.message_id: mail.email_bcc for mail in self if mail.email_bcc and mail.message_id}
        if bcc_map:
            self = self.with_context(mail_bcc_by_message_id=bcc_map)
        return super(MailMail, self)._send(*args, **kwargs)

    @api.model
    def _bcc_addresses(self, value):
        return email_normalize_all(value or '')
