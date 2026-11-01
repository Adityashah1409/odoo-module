from odoo import api, fields, models

from .mail_cc_rule import check_emails


class ResCompany(models.Model):
    _inherit = 'res.company'

    mail_default_cc = fields.Char('Default Cc', help='Added in Cc of the e-mails written in the composer.')
    mail_default_bcc = fields.Char('Default Bcc', help='Added in Bcc of the e-mails written in the composer.')
    mail_default_reply_to = fields.Char('Default Reply-To',
                                        help='Answers go to this address instead of the chatter of the document.')

    @api.constrains('mail_default_cc', 'mail_default_bcc', 'mail_default_reply_to')
    def _check_mail_defaults(self):
        for company in self:
            check_emails(self.env, company.mail_default_cc, company.mail_default_bcc, company.mail_default_reply_to)
