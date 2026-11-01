from odoo import fields, models


class MailMessage(models.Model):
    _inherit = 'mail.message'

    extra_email_cc = fields.Char('Cc (e-mails)', help='Addresses in Cc of the e-mail sent for this message.')
    extra_email_bcc = fields.Char('Bcc (e-mails)', groups='base.group_user',
                                  help='Hidden copies of the e-mail sent for this message.')
