import base64
import logging
import mimetypes

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from .whapi_account import digits, ts_to_datetime

_logger = logging.getLogger(__name__)

STATES = [('received', 'Received'), ('draft', 'Draft'), ('sent', 'Sent'), ('delivered', 'Delivered'),
          ('read', 'Read'), ('failed', 'Failed'), ('deleted', 'Deleted')]
PROGRESS = {'draft': 0, 'sent': 1, 'delivered': 2, 'read': 3}
MEDIA_TYPES = ('image', 'video', 'audio', 'voice', 'document', 'sticker', 'gif', 'short')


class WhapiMessage(models.Model):
    _name = 'whapi.message'
    _description = 'WhatsApp message'
    _order = 'date desc, id desc'
    _rec_name = 'preview'

    chat_id = fields.Many2one('whapi.chat', required=True, ondelete='cascade', index=True)
    account_id = fields.Many2one(related='chat_id.account_id', store=True, index=True)
    company_id = fields.Many2one(related='chat_id.company_id', store=True)
    wa_id = fields.Char('WhatsApp id', index=True, copy=False)
    direction = fields.Selection([('in', 'Received'), ('out', 'Sent')], required=True, default='out')
    msg_type = fields.Selection([('text', 'Text'), ('image', 'Image'), ('video', 'Video'), ('audio', 'Audio'),
                                 ('voice', 'Voice'), ('document', 'Document'), ('sticker', 'Sticker'),
                                 ('location', 'Location'), ('contact', 'Contact card'), ('system', 'System'),
                                 ('other', 'Other')], string='Type', default='text', required=True)
    body = fields.Text()
    preview = fields.Char(compute='_compute_preview')
    author_wa_id = fields.Char('From')
    author_name = fields.Char()
    partner_id = fields.Many2one('res.partner', string='Contact', index=True)
    user_id = fields.Many2one('res.users', string='Sent by', default=lambda self: self.env.user)
    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    state = fields.Selection(STATES, default='draft', required=True, index=True,
                             group_expand='_group_expand_states')
    error = fields.Char()
    attachment_ids = fields.Many2many('ir.attachment', string='Files')
    reply_to_id = fields.Many2one('whapi.message', string='Reply to', ondelete='set null')
    forwarded = fields.Boolean()
    starred = fields.Boolean()
    status_ids = fields.One2many('whapi.message.status', 'message_id', string='Receipts')
    res_model = fields.Char('Document model')
    res_id = fields.Many2oneReference('Document', model_field='res_model')

    @api.model
    def _group_expand_states(self, states, domain):
        """Kanban columns: every state except draft (shown only when a message is stuck in it)."""
        return [key for key, _label in STATES if key != 'draft' or key in states]

    @api.depends('body', 'msg_type', 'attachment_ids', 'state')
    def _compute_preview(self):
        labels = dict(self._fields['msg_type'].selection)
        for message in self:
            if message.state == 'deleted':
                message.preview = self.env._('This message was deleted')
            elif message.body:
                message.preview = message.body.replace('\n', ' ')[:80]
            elif message.attachment_ids:
                message.preview = f'📎 {message.attachment_ids[0].name}'
            else:
                message.preview = labels.get(message.msg_type, '')

    # ------------------------------------------------------------------
    # sending
    # ------------------------------------------------------------------
    @api.model
    def _whapi_send_to_chat(self, chat, body='', attachments=None, reply_to=None, voice=False, record=None):
        """Create and send the message(s): one per file (the first one carries the text), or one text message."""
        chat.ensure_one()
        if chat.blocked:
            raise UserError(self.env._('This chat is ignored.'))
        attachments = attachments or self.env['ir.attachment']
        body = (body or '').strip()
        if not body and not attachments:
            raise UserError(self.env._('Nothing to send.'))
        base = {'chat_id': chat.id, 'direction': 'out', 'partner_id': chat.partner_id.id,
                'reply_to_id': reply_to and reply_to.id, 'author_wa_id': chat.account_id.phone,
                'author_name': self.env.user.name,
                'res_model': record and record._name, 'res_id': record and record.id}
        vals_list = []
        if attachments:
            for index, attachment in enumerate(attachments):
                vals_list.append(dict(base, body=body if index == 0 else False,
                                      msg_type=self._whapi_type_for(attachment, voice),
                                      attachment_ids=[(6, 0, attachment.ids)]))
        else:
            vals_list.append(dict(base, body=body, msg_type='text'))
        messages = self.create(vals_list)
        for attachment, message in zip(attachments, messages):
            attachment.sudo().write({'res_model': 'whapi.message', 'res_id': message.id})
        messages._whapi_send()
        return messages

    @api.model
    def _whapi_type_for(self, attachment, voice=False):
        mimetype = attachment.mimetype or ''
        if mimetype.startswith('image/'):
            return 'sticker' if mimetype == 'image/webp' and attachment.name.endswith('.sticker.webp') else 'image'
        if mimetype.startswith('video/'):
            return 'video'
        if mimetype.startswith('audio/'):
            return 'voice' if voice else 'audio'
        return 'document'

    def _whapi_send(self):
        for message in self:
            chat = message.chat_id
            account = chat.account_id
            payload = {'to': chat.wa_id}
            if message.reply_to_id.wa_id:
                payload['quoted'] = message.reply_to_id.wa_id
            if message.msg_type == 'text':
                endpoint = '/messages/text'
                payload['body'] = message.body
            else:
                attachment = message.attachment_ids[:1]
                endpoint = f'/messages/{message.msg_type}'
                payload['media'] = account._whapi_media_data_url(attachment)
                if message.body and message.msg_type not in ('voice', 'audio', 'sticker'):
                    payload['caption'] = message.body
                if message.msg_type == 'document':
                    payload['filename'] = attachment.name
            try:
                result = account._whapi_request('POST', endpoint, payload)
            except UserError as error:
                message.write({'state': 'failed', 'error': str(error)[:250]})
                continue
            sent = result.get('message') or {}
            message.write({'state': 'sent', 'wa_id': sent.get('id') or message.wa_id, 'error': False})
            message._whapi_after_post()

    def action_retry(self):
        self.filtered(lambda m: m.state == 'failed' and m.direction == 'out')._whapi_send()

    def whapi_forward(self, chat_ids):
        """Forward this message to several chats at once."""
        self.ensure_one()
        chats = self.env['whapi.chat'].browse(chat_ids).exists()
        if not chats:
            raise UserError(self.env._('Choose at least one chat.'))
        forwarded = self.env['whapi.message']
        for chat in chats:
            new = self.create({
                'chat_id': chat.id, 'direction': 'out', 'partner_id': chat.partner_id.id, 'body': self.body,
                'msg_type': self.msg_type, 'forwarded': True, 'author_wa_id': chat.account_id.phone,
                'author_name': self.env.user.name, 'attachment_ids': [(6, 0, self.attachment_ids.ids)],
            })
            if self.wa_id and not self.wa_id.startswith('sandbox-') and chat.account_id == self.account_id:
                try:
                    result = chat.account_id._whapi_request('POST', f'/messages/{self.wa_id}', {'to': chat.wa_id})
                    new.write({'state': 'sent', 'wa_id': (result.get('message') or {}).get('id')
                               or result.get('id') or False})
                    new._whapi_after_post()
                except UserError as error:
                    new.write({'state': 'failed', 'error': str(error)[:250]})
            else:
                new._whapi_send()
            forwarded |= new
        return len(forwarded)

    def whapi_toggle_star(self):
        for message in self:
            message.starred = not message.starred
        return self[:1].starred

    def whapi_delete(self):
        for message in self.filtered(lambda m: m.state != 'deleted'):
            if message.direction == 'out' and message.wa_id and not message.wa_id.startswith('sandbox-'):
                message.account_id._whapi_request('DELETE', f'/messages/{message.wa_id}')
            message._whapi_mark_deleted()
        return True

    def _whapi_mark_deleted(self):
        self.write({'state': 'deleted', 'starred': False})
        self.chat_id._whapi_notify({'message_ids': self.ids})

    def whapi_info(self):
        self.ensure_one()
        chat = self.chat_id
        statuses = [{'name': s.name or ('+' + s.recipient), 'status': s.status,
                     'date': fields.Datetime.to_string(s.date)} for s in self.status_ids]
        pending = []
        if chat.chat_type == 'group' and self.direction == 'out':
            done = {s.recipient for s in self.status_ids if s.status == 'read'}
            pending = [p.name or ('+' + p.wa_id) for p in chat.participant_ids
                       if p.wa_id not in done and p.wa_id != digits(chat.account_id.phone)]
        return {'message': self._whapi_message_dict(), 'statuses': statuses, 'pending': pending}

    # ------------------------------------------------------------------
    # receiving
    # ------------------------------------------------------------------
    @api.model
    def _whapi_from_webhook(self, account, data):
        """Create (or update) the message of a ``messages`` webhook item."""
        chat_wa_id = data.get('chat_id') or ''
        if not chat_wa_id or chat_wa_id.endswith('@broadcast') or chat_wa_id.endswith('@newsletter'):
            return False
        if chat_wa_id.endswith('@g.us') and not account.sync_groups:
            return False
        if data.get('type') == 'action':
            return self._whapi_action_from_webhook(account, data)
        existing = self.search([('wa_id', '=', data.get('id')), ('account_id', '=', account.id)], limit=1) \
            if data.get('id') else self
        if existing:
            return existing
        chat = account._whapi_get_chat(chat_wa_id, data.get('chat_name') or (
            None if chat_wa_id.endswith('@g.us') else data.get('from_name')))
        if chat.blocked:
            return False
        if not chat.active:
            chat.active = True
        from_me = bool(data.get('from_me'))
        msg_type, body, media = self._whapi_parse_content(data)
        author = digits(data.get('from'))
        partner = chat.partner_id if chat.chat_type == 'contact' else \
            chat.participant_ids.filtered(lambda p: p.wa_id == author)[:1].partner_id
        context = data.get('context') or {}
        reply_to = self.search([('wa_id', '=', context['quoted_id']), ('chat_id', '=', chat.id)], limit=1) \
            if context.get('quoted_id') else self
        message = self.create({
            'chat_id': chat.id, 'wa_id': data.get('id'), 'direction': 'out' if from_me else 'in',
            'msg_type': msg_type, 'body': body, 'author_wa_id': author, 'partner_id': partner.id,
            'author_name': data.get('from_name') or partner.name or (author and '+' + author),
            'date': ts_to_datetime(data.get('timestamp')) or fields.Datetime.now(),
            'state': 'sent' if from_me else 'received', 'reply_to_id': reply_to.id,
            'forwarded': bool(context.get('forwarded')), 'user_id': False,
        })
        if media:
            attachment = self._whapi_download_media(account, media, msg_type, message)
            if attachment:
                message.attachment_ids = [(4, attachment.id)]
        message._whapi_after_post(incoming=not from_me)
        return message

    @api.model
    def _whapi_parse_content(self, data):
        msg_type = data.get('type') or 'text'
        if msg_type == 'text':
            return 'text', (data.get('text') or {}).get('body', ''), None
        if msg_type == 'link_preview':
            return 'text', (data.get('link_preview') or {}).get('body', ''), None
        if msg_type in MEDIA_TYPES:
            media = data.get(msg_type) or {}
            mapped = {'gif': 'video', 'short': 'video'}.get(msg_type, msg_type)
            return mapped, media.get('caption') or '', media
        if msg_type in ('location', 'live_location'):
            loc = data.get(msg_type) or {}
            label = ', '.join(filter(None, [loc.get('name'), loc.get('address')]))
            url = f"https://maps.google.com/?q={loc.get('latitude')},{loc.get('longitude')}"
            return 'location', f'📍 {label}\n{url}'.strip(), None
        if msg_type in ('contact', 'contact_list'):
            card = data.get('contact') or {}
            return 'contact', f"👤 {card.get('name') or self.env._('Contact card')}", None
        if msg_type == 'system':
            return 'system', (data.get('system') or {}).get('body', ''), None
        return 'other', data.get('text', {}).get('body', '') if isinstance(data.get('text'), dict) else '', None

    @api.model
    def _whapi_download_media(self, account, media, msg_type, message):
        content = b''
        try:
            if media.get('id'):
                content = account._whapi_request('GET', f"/media/{media['id']}", raw=True)
        except UserError as error:
            _logger.info('Whapi media %s not downloaded: %s', media.get('id'), error)
        mimetype = (media.get('mime_type') or 'application/octet-stream').split(';')[0]
        extension = mimetypes.guess_extension(mimetype) or ''
        name = media.get('filename') or media.get('file_name') or f'{msg_type}-{message.id}{extension}'
        if not content:
            if not media.get('link'):
                return False
            return self.env['ir.attachment'].sudo().create({
                'name': name, 'type': 'url', 'url': media['link'], 'mimetype': mimetype,
                'res_model': 'whapi.message', 'res_id': message.id})
        return self.env['ir.attachment'].sudo().create({
            'name': name, 'raw': content, 'mimetype': mimetype,
            'res_model': 'whapi.message', 'res_id': message.id})

    @api.model
    def _whapi_action_from_webhook(self, account, data):
        action = data.get('action') or {}
        target = self.search([('wa_id', '=', action.get('target')), ('account_id', '=', account.id)], limit=1)
        if not target:
            return False
        if action.get('type') in ('delete', 'revoke'):
            target._whapi_mark_deleted()
        elif action.get('type') == 'edit' and action.get('edited_content'):
            content = action['edited_content']
            target.body = (content.get('text') or {}).get('body') or content.get('body') or target.body
            target.chat_id._whapi_notify({'message_ids': target.ids})
        return target

    @api.model
    def _whapi_status_from_webhook(self, account, data):
        message = self.search([('wa_id', '=', data.get('id')), ('account_id', '=', account.id)], limit=1)
        if not message:
            return False
        status = data.get('status') or ''
        status = {'played': 'read', 'pending': 'sent'}.get(status, status)
        recipient = digits(data.get('viewer_id') or data.get('recipient_id') or '')
        date = ts_to_datetime(data.get('timestamp')) or fields.Datetime.now()
        if status == 'failed':
            message.write({'state': 'failed', 'error': data.get('error') or self.env._('Not delivered')})
        elif status == 'deleted':
            message._whapi_mark_deleted()
            return message
        elif status in PROGRESS:
            if message.chat_id.chat_type == 'group' and recipient:
                line = message.status_ids.filtered(lambda s: s.recipient == recipient)
                participant = message.chat_id.participant_ids.filtered(lambda p: p.wa_id == recipient)[:1]
                if line:
                    if PROGRESS[status] > PROGRESS.get(line.status, 0):
                        line.write({'status': status, 'date': date})
                else:
                    self.env['whapi.message.status'].sudo().create({
                        'message_id': message.id, 'recipient': recipient, 'status': status, 'date': date,
                        'name': participant.name or False})
                # the group message is "read" once every participant has read it
                members = len(message.chat_id.participant_ids.filtered(
                    lambda p: p.wa_id != digits(account.phone))) or 1
                reads = len(message.status_ids.filtered(lambda s: s.status == 'read'))
                delivered = len(message.status_ids.filtered(lambda s: s.status in ('delivered', 'read')))
                status = 'read' if reads >= members else 'delivered' if delivered else status
            elif not message.chat_id.chat_type == 'group':
                line = message.status_ids[:1]
                values = {'status': status, 'date': date, 'recipient': recipient or digits(message.chat_id.wa_id)}
                if line:
                    if PROGRESS[status] > PROGRESS.get(line.status, 0):
                        line.write(values)
                else:
                    self.env['whapi.message.status'].sudo().create(dict(values, message_id=message.id))
            if message.state in PROGRESS and PROGRESS[status] > PROGRESS[message.state]:
                message.state = status
        message.chat_id._whapi_notify({'message_ids': message.ids})
        return message

    # ------------------------------------------------------------------
    # after a message is posted (both ways)
    # ------------------------------------------------------------------
    def _whapi_after_post(self, incoming=False):
        for message in self:
            chat = message.chat_id.sudo()
            values = {'last_message_at': max(filter(None, [chat.last_message_at, message.date])),
                      'last_message_preview': ('' if incoming else '✓ ') + (message.preview or '')}
            if incoming:
                values['unread_count'] = chat.unread_count + 1
            chat.write(values)
            if chat.account_id.log_in_chatter and message.partner_id and chat.chat_type == 'contact':
                message._whapi_log_in_chatter()
            if message.res_model and message.res_id and message.direction == 'out':
                record = self.env[message.res_model].browse(message.res_id).exists()
                if record and hasattr(record, 'message_post') and record._name != 'res.partner':
                    record.sudo().message_post(
                        body=Markup('<p><b>%s</b></p><p>%s</p>') % (
                            self.env._('WhatsApp sent to %s', chat.name), message.body or message.preview),
                        attachment_ids=message.attachment_ids.ids, subtype_xmlid='mail.mt_note')
        self.chat_id._whapi_notify({'message_ids': self.ids, 'incoming': incoming,
                                    'preview': self[:1].preview, 'author': self[:1].author_name})

    def _whapi_log_in_chatter(self):
        self.ensure_one()
        arrow = '⬅️' if self.direction == 'in' else '➡️'
        label = self.env._('WhatsApp received') if self.direction == 'in' else self.env._('WhatsApp sent')
        self.partner_id.sudo().message_post(
            body=Markup('<p>%s <b>%s</b></p><p>%s</p>') % (arrow, label, self.body or self.preview or ''),
            subtype_xmlid='mail.mt_note', author_id=self.partner_id.id if self.direction == 'in' else None)

    # ------------------------------------------------------------------
    # chat screen data
    # ------------------------------------------------------------------
    def _whapi_message_dict(self):
        self.ensure_one()
        deleted = self.state == 'deleted'
        reply = self.reply_to_id
        return {
            'id': self.id, 'chat_id': self.chat_id.id, 'direction': self.direction, 'type': self.msg_type,
            'body': '' if deleted else (self.body or ''), 'state': self.state, 'error': self.error or '',
            'date': fields.Datetime.to_string(self.date), 'author': self.author_name or '',
            'forwarded': self.forwarded, 'starred': self.starred, 'deleted': deleted,
            'attachments': [] if deleted else [a._whapi_attachment_dict() for a in self.attachment_ids],
            'reply': {'id': reply.id, 'author': reply.author_name or '', 'preview': reply.preview or ''}
            if reply else False,
        }

    @api.model
    def _whapi_body_from_html(self, html):
        return html2plaintext(html or '').strip()


class WhapiMessageStatus(models.Model):
    _name = 'whapi.message.status'
    _description = 'WhatsApp read receipt'
    _order = 'date desc, id desc'

    message_id = fields.Many2one('whapi.message', required=True, ondelete='cascade', index=True)
    recipient = fields.Char(required=True)
    name = fields.Char()
    status = fields.Selection([('sent', 'Sent'), ('delivered', 'Delivered'), ('read', 'Read')], required=True)
    date = fields.Datetime(default=fields.Datetime.now)


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def _whapi_attachment_dict(self):
        self.ensure_one()
        url = self.url if self.type == 'url' else f'/web/content/{self.id}?download=false'
        return {'id': self.id, 'name': self.name, 'mimetype': self.mimetype or '', 'url': url,
                'download': self.url if self.type == 'url' else f'/web/content/{self.id}?download=true',
                'size': self.file_size or 0}
