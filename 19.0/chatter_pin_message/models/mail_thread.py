from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.mail.tools.discuss import Store

PINNABLE_TYPES = ('comment', 'email', 'email_outgoing')


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _chatter_pin_check_rights(self):
        if not self.env.user._is_internal():
            raise AccessError(self.env._('Only internal users can pin messages.'))
        access = self.env['ir.config_parameter'].sudo().get_param('chatter_pin_message.access') or 'write'
        self.check_access('read' if access == 'read' else 'write')

    def _chatter_pinned_domain(self):
        return [('model', '=', self._name), ('res_id', '=', self.id), ('pinned_at', '!=', False)]

    def _chatter_pin_data(self, messages):
        return {
            'store': Store().add(messages).get_result(),
            'pinned_by': {
                # sudo: res.users - the name of who pinned is shown to everyone who sees the message
                message.id: {'name': message.sudo().pinned_by_id.name or '', 'pinned_at': message.pinned_at}
                for message in messages if message.pinned_at
            },
        }

    def chatter_set_message_pin(self, message_id, pinned):
        """ (Un)pin a message of this record's chatter. """
        self.ensure_one()
        self._chatter_pin_check_rights()
        message = self.env['mail.message'].search([
            ('id', '=', message_id), ('model', '=', self._name), ('res_id', '=', self.id),
        ])
        if not message:
            raise UserError(self.env._('This message does not belong to this record.'))
        if message.message_type not in PINNABLE_TYPES:
            raise UserError(self.env._('Only messages and notes can be pinned.'))
        if pinned and not message.pinned_at:
            limit = int(self.env['ir.config_parameter'].sudo().get_param('chatter_pin_message.max', 5) or 0)
            if limit and self.env['mail.message'].sudo().search_count(self._chatter_pinned_domain()) >= limit:
                raise UserError(self.env._(
                    'This record already has %(limit)s pinned messages. Unpin one first.', limit=limit))
        if bool(message.pinned_at) != bool(pinned):
            message.flush_recordset(['pinned_at', 'pinned_by_id'])
            # SQL: pinning must not change the write date nor need write access on the message
            self.env.cr.execute(
                'UPDATE mail_message SET pinned_at = %s, pinned_by_id = %s WHERE id = %s',
                (fields.Datetime.now() if pinned else None, self.env.uid if pinned else None, message.id))
            message.invalidate_recordset(['pinned_at', 'pinned_by_id'])
        return self._chatter_pin_data(message)

    @api.readonly
    def chatter_pinned_messages(self):
        """ Pinned messages of this record, also the ones not loaded yet in the chatter. """
        self.ensure_one()
        self.check_access('read')
        messages = self.env['mail.message'].search(self._chatter_pinned_domain(), order='pinned_at desc')
        return self._chatter_pin_data(messages)
