from markupsafe import Markup

from odoo import api, fields, models

from ..models.mail_cc_rule import check_emails, split_emails


class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'

    extra_email_cc = fields.Char('Cc', compute='_compute_extra_email_cc', store=True, readonly=False,
                                 help='E-mail addresses in copy, separated by commas.')
    extra_email_bcc = fields.Char('Bcc', compute='_compute_extra_email_bcc', store=True, readonly=False,
                                  help='Hidden copies, separated by commas.')

    def _extra_email_defaults(self):
        self.ensure_one()
        if not self.model or self.model not in self.env or self.subtype_is_log:
            return {'cc': [], 'bcc': [], 'reply_to': False}
        return self.env['mail.cc.rule']._get_defaults(self.model)

    # one compute per field: a value given for one of them must not block the other
    @api.depends('model', 'composition_mode', 'subtype_is_log')
    def _compute_extra_email_cc(self):
        for composer in self:
            composer.extra_email_cc = ', '.join(composer._extra_email_defaults()['cc']) or False

    @api.depends('model', 'composition_mode', 'subtype_is_log')
    def _compute_extra_email_bcc(self):
        for composer in self:
            composer.extra_email_bcc = ', '.join(composer._extra_email_defaults()['bcc']) or False

    @api.depends('composition_mode', 'model', 'res_domain', 'res_ids', 'template_id')
    def _compute_reply_to(self):
        super()._compute_reply_to()
        for composer in self:
            if composer.composition_mode == 'comment' and not composer.reply_to:
                composer.reply_to = composer._extra_email_defaults()['reply_to']

    def _prepare_mail_values(self, res_ids):
        check_emails(self.env, self.extra_email_cc, self.extra_email_bcc)
        results = super()._prepare_mail_values(res_ids)
        if not (self.extra_email_cc or self.extra_email_bcc) or self.subtype_is_log:
            return results
        cc = ', '.join(split_emails(self.extra_email_cc)) or False
        bcc = ', '.join(split_emails(self.extra_email_bcc)) or False
        for values in results.values():
            if self.composition_mode == 'comment':
                values.update({'extra_email_cc': cc, 'extra_email_bcc': bcc})
            else:
                values['email_cc'] = ', '.join(split_emails(values.get('email_cc'), cc)) or False
                values['email_bcc'] = bcc
        return results

    def _action_send_mail_comment(self, res_ids):
        messages = super()._action_send_mail_comment(res_ids)
        if (self.extra_email_cc or self.extra_email_bcc) and not self.subtype_is_log:
            for message in messages:
                record = self.env[message.model].browse(message.res_id) if message.model else None
                if record:
                    parts = []
                    if self.extra_email_cc:
                        parts.append(self.env._('Cc: %s', self.extra_email_cc))
                    if self.extra_email_bcc:
                        parts.append(self.env._('Bcc: %s', self.extra_email_bcc))
                    if self.reply_to:
                        parts.append(self.env._('Reply-To: %s', self.reply_to))
                    record.sudo().message_post(body=Markup('<br/>').join(parts), subtype_xmlid='mail.mt_note',
                                               message_type='notification')
        return messages
