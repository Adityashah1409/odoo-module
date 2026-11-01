from odoo import models
from odoo.exceptions import AccessError, UserError

PINNABLE_TYPES = ('comment', 'email', 'email_outgoing')


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _chatter_pin_check_rights(self):
        if not self.env.user._is_internal():
            raise AccessError(self.env._('Only internal users can pin messages.'))
        access = self.env['ir.config_parameter'].sudo().get_str('chatter_pin_message.access') or 'write'
        self.check_access('read' if access == 'read' else 'write')

    def _chatter_pinned_domain(self):
        return [('model', '=', self._name), ('res_id', '=', self.id), ('pinned_at', '!=', False)]

    def set_message_pin(self, message_id, pinned):
        """ Odoo 20 pins messages in the chatter natively: add the rules and remember who pinned. """
        self.ensure_one()
        if self._name != 'discuss.channel':
            self._chatter_pin_check_rights()
            message = self.env['mail.message'].search([
                ('id', '=', message_id), ('model', '=', self._name), ('res_id', '=', self.id),
            ])
            if not message:
                raise UserError(self.env._('This message does not belong to this record.'))
            if message.message_type not in PINNABLE_TYPES:
                raise UserError(self.env._('Only messages and notes can be pinned.'))
            if pinned and not message.pinned_at:
                limit = self.env['ir.config_parameter'].sudo().get_int('chatter_pin_message.max', 5)
                if limit and self.env['mail.message'].sudo().search_count(self._chatter_pinned_domain()) >= limit:
                    raise UserError(self.env._(
                        'This record already has %(limit)s pinned messages. Unpin one first.', limit=limit))
        result = super().set_message_pin(message_id, pinned)
        if result:
            # SQL, like Odoo's own pin: the message itself is not modified
            self.env.cr.execute('UPDATE mail_message SET pinned_by_id = %s WHERE id = %s',
                                (self.env.uid if pinned else None, message_id))
            self.env['mail.message'].browse(message_id).invalidate_recordset(['pinned_by_id'])
        return result
