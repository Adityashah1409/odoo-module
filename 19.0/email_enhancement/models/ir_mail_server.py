from odoo import api, models
from odoo.tools.mail import email_normalize_all


class IrMailServer(models.Model):
    _inherit = 'ir.mail_server'

    @api.model
    def _prepare_smtp_to_list(self, message, smtp_session):
        """ Add the Bcc of the e-mail to the SMTP envelope only: they never appear in the headers. """
        smtp_to_list = super()._prepare_smtp_to_list(message, smtp_session)
        bcc_map = self.env.context.get('mail_bcc_by_message_id')
        if bcc_map and message['Message-Id'] in bcc_map:
            # once per e-mail, even when it is sent in several personalized copies
            bcc = email_normalize_all(bcc_map.pop(message['Message-Id']) or '')
            smtp_to_list += [address for address in bcc if address not in smtp_to_list]
        return smtp_to_list
