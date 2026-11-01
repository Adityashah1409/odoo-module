from odoo import models

PENDING_KEY = '_email_enhancement_pending'


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _get_message_create_valid_field_names(self):
        return super()._get_message_create_valid_field_names() | {'extra_email_cc', 'extra_email_bcc'}

    def _notify_by_email_get_base_mail_values(self, message, recipients_data, additional_values=None):
        values = super()._notify_by_email_get_base_mail_values(message, recipients_data, additional_values)
        message_sudo = message.sudo()
        if message_sudo.extra_email_cc or message_sudo.extra_email_bcc:
            # Cc / Bcc go on the first e-mail only (a message may be sent as several e-mails)
            values[PENDING_KEY] = {'email_cc': message_sudo.extra_email_cc or False,
                                   'email_bcc': message_sudo.extra_email_bcc or False}
        return values

    def _notify_by_email_get_final_mail_values(self, recipient_ids, mail_values,
                                               recipient_cc_ids=None, additional_values=None):
        base_mail_values = mail_values
        values = super()._notify_by_email_get_final_mail_values(
            recipient_ids, mail_values, recipient_cc_ids=recipient_cc_ids, additional_values=additional_values)
        values.pop(PENDING_KEY, None)
        pending = base_mail_values.pop(PENDING_KEY, None)
        if pending:
            values.update(pending)
        return values
