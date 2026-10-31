import base64

from odoo import api, fields, models
from odoo.exceptions import UserError

from .whapi_account import digits


class WhapiChat(models.Model):
    _name = 'whapi.chat'
    _description = 'WhatsApp chat'
    _order = 'pinned desc, last_message_at desc, id desc'

    account_id = fields.Many2one('whapi.account', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='account_id.company_id', store=True)
    wa_id = fields.Char('WhatsApp id', required=True, index=True,
                        help='31612345678@s.whatsapp.net for a contact, ...@g.us for a group.')
    name = fields.Char(required=True)
    chat_type = fields.Selection([('contact', 'Contact'), ('group', 'Group')], default='contact', required=True)
    phone = fields.Char(compute='_compute_phone', store=True)
    partner_id = fields.Many2one('res.partner', string='Contact', index=True)
    active = fields.Boolean(default=True)
    blocked = fields.Boolean('Ignored', help='Incoming messages of this chat are dropped.')
    pinned = fields.Boolean()
    description = fields.Text()
    last_message_at = fields.Datetime(readonly=True)
    last_message_preview = fields.Char(readonly=True)
    unread_count = fields.Integer(readonly=True)
    message_ids = fields.One2many('whapi.message', 'chat_id')
    message_count = fields.Integer(compute='_compute_message_count')
    participant_ids = fields.One2many('whapi.chat.participant', 'chat_id')
    event_ids = fields.One2many('whapi.chat.event', 'chat_id')

    _unique_wa_id = models.UniqueIndex('(account_id, wa_id)')

    @api.depends('wa_id', 'chat_type')
    def _compute_phone(self):
        for chat in self:
            chat.phone = '+' + chat.wa_id.split('@')[0] if chat.chat_type == 'contact' and chat.wa_id else False

    def _compute_message_count(self):
        counts = dict(self.env['whapi.message']._read_group([('chat_id', 'in', self.ids)], ['chat_id'], ['__count']))
        for chat in self:
            chat.message_count = counts.get(chat, 0)

    @api.model
    def _whapi_find_partner(self, number):
        """Contact whose phone is ``number`` (digits, international format)."""
        number = digits(number)
        if len(number) < 6:
            return self.env['res.partner']
        candidates = self.env['res.partner'].sudo().search([('phone', 'ilike', number[-6:])], limit=50)
        for partner in candidates:
            phone = digits(partner.phone)
            if phone and (phone == number or (len(phone) >= 8 and number.endswith(phone.lstrip('0')))):
                return partner
        # the stored phone may have separators inside the last digits
        for partner in self.env['res.partner'].sudo().search([('phone', '!=', False)], limit=2000):
            phone = digits(partner.phone)
            if phone and (phone == number or (len(phone) >= 8 and number.endswith(phone.lstrip('0')))):
                return partner
        return self.env['res.partner']

    def action_open(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'whatsapp_whapi.chat', 'name': self.name,
                'params': {'chat_id': self.id, 'account_id': self.account_id.id}}

    def action_view_messages(self):
        action = self.env['ir.actions.act_window']._for_xml_id('whatsapp_whapi.action_whapi_message')
        action['domain'] = [('chat_id', '=', self.id)]
        return action

    def action_link_partner(self):
        for chat in self.filtered(lambda c: c.chat_type == 'contact' and not c.partner_id):
            chat.partner_id = self._whapi_find_partner(chat.wa_id.split('@')[0])

    def action_refresh_group(self):
        for chat in self.filtered(lambda c: c.chat_type == 'group'):
            info = chat.account_id._whapi_request('GET', f'/groups/{chat.wa_id}')
            chat.write({'name': info.get('name') or chat.name, 'description': info.get('description') or False})
            chat._whapi_set_participants(info.get('participants') or [])

    # ------------------------------------------------------------------
    # groups
    # ------------------------------------------------------------------
    def _whapi_set_participants(self, participants):
        self.ensure_one()
        existing = {p.wa_id: p for p in self.participant_ids}
        seen = set()
        for item in participants:
            wa_id = digits(item.get('id') if isinstance(item, dict) else item)
            if not wa_id:
                continue
            seen.add(wa_id)
            rank = (item.get('rank') if isinstance(item, dict) else None) or 'member'
            rank = rank if rank in ('member', 'admin', 'creator') else 'member'
            if wa_id in existing:
                if existing[wa_id].rank != rank:
                    existing[wa_id].rank = rank
            else:
                own = wa_id == digits(self.account_id.phone)
                partner = self.env['res.partner'] if own else self._whapi_find_partner(wa_id)
                name = (self.account_id.wa_name or self.account_id.name) if own else \
                    partner.name or (item.get('name') if isinstance(item, dict) else False)
                self.env['whapi.chat.participant'].sudo().create({
                    'chat_id': self.id, 'wa_id': wa_id, 'rank': rank, 'partner_id': partner.id, 'name': name,
                })
        self.participant_ids.filtered(lambda p: p.wa_id not in seen).unlink()

    def _whapi_participants_event(self, data):
        """Webhook ``groups_participants``: add / remove / promote / demote."""
        self.ensure_one()
        action = data.get('action')
        kinds = {'add': 'join', 'remove': 'leave', 'promote': 'promote', 'demote': 'demote'}
        Participant = self.env['whapi.chat.participant'].sudo()
        for raw in data.get('participants') or []:
            wa_id = digits(raw)
            participant = self.participant_ids.filtered(lambda p: p.wa_id == wa_id)
            if action == 'add' and not participant:
                partner = self._whapi_find_partner(wa_id)
                Participant.create({'chat_id': self.id, 'wa_id': wa_id, 'partner_id': partner.id,
                                    'name': partner.name or False})
            elif action == 'remove':
                participant.unlink()
            elif action in ('promote', 'demote') and participant:
                participant.rank = 'admin' if action == 'promote' else 'member'
            if action in kinds:
                self.env['whapi.chat.event'].sudo().create({
                    'chat_id': self.id, 'kind': kinds[action], 'participant': wa_id,
                    'author': digits(data.get('author') or data.get('from') or ''),
                })
        self._whapi_notify({'chat_id': self.id, 'group': True})

    def whapi_add_participants(self, phones):
        self.ensure_one()
        numbers = [digits(p) for p in phones if digits(p)]
        if not numbers:
            raise UserError(self.env._('Give at least one phone number.'))
        self.account_id._whapi_request('POST', f'/groups/{self.wa_id}/participants', {'participants': numbers})
        self._whapi_participants_event({'action': 'add', 'participants': numbers,
                                        'author': self.account_id.phone})
        return self.whapi_group_info()

    def whapi_remove_participant(self, participant_id):
        self.ensure_one()
        participant = self.participant_ids.filtered(lambda p: p.id == participant_id)
        self.account_id._whapi_request('DELETE', f'/groups/{self.wa_id}/participants',
                                       {'participants': [participant.wa_id]})
        self._whapi_participants_event({'action': 'remove', 'participants': [participant.wa_id],
                                        'author': self.account_id.phone})
        return self.whapi_group_info()

    def whapi_set_admin(self, participant_id, admin=True):
        self.ensure_one()
        participant = self.participant_ids.filtered(lambda p: p.id == participant_id)
        self.account_id._whapi_request('PATCH' if admin else 'DELETE', f'/groups/{self.wa_id}/admins',
                                       {'participants': [participant.wa_id]})
        self._whapi_participants_event({'action': 'promote' if admin else 'demote',
                                        'participants': [participant.wa_id], 'author': self.account_id.phone})
        return self.whapi_group_info()

    # ------------------------------------------------------------------
    # data for the chat screen
    # ------------------------------------------------------------------
    def _whapi_chat_dict(self):
        self.ensure_one()
        return {
            'id': self.id, 'name': self.name, 'type': self.chat_type, 'phone': self.phone or '',
            'partner_id': self.partner_id.id, 'partner_name': self.partner_id.name or '',
            'account_id': self.account_id.id, 'account_name': self.account_id.name,
            'last_message_at': fields.Datetime.to_string(self.last_message_at) if self.last_message_at else False,
            'preview': self.last_message_preview or '', 'unread': self.unread_count, 'pinned': self.pinned,
            'blocked': self.blocked, 'participants': len(self.participant_ids),
        }

    @api.model
    def whapi_load_chats(self, account_id=False, search='', mode='all', limit=80):
        accounts = self.env['whapi.account'].search([('id', '=', account_id)] if account_id else [])
        domain = [('account_id', 'in', accounts.ids), ('blocked', '=', False)]
        if not accounts.filtered('sync_groups'):
            domain.append(('chat_type', '=', 'contact'))
        if mode == 'unread':
            domain.append(('unread_count', '>', 0))
        elif mode == 'groups':
            domain.append(('chat_type', '=', 'group'))
        if search:
            domain += ['|', '|', ('name', 'ilike', search), ('wa_id', 'ilike', search),
                       ('partner_id.name', 'ilike', search)]
        chats = self.search(domain, limit=limit)
        return {
            'chats': [chat._whapi_chat_dict() for chat in chats],
            'accounts': [{'id': a.id, 'name': a.name, 'state': a.state, 'sandbox': a.sandbox,
                          'phone': a.phone or ''} for a in accounts],
        }

    def whapi_load_messages(self, before_id=False, limit=60):
        self.ensure_one()
        domain = [('chat_id', '=', self.id)]
        if before_id:
            domain.append(('id', '<', before_id))
        messages = self.env['whapi.message'].search(domain, order='id desc', limit=limit)
        return {
            'chat': self._whapi_chat_dict(),
            'messages': [m._whapi_message_dict() for m in reversed(messages)],
            'more': len(messages) == limit,
        }

    def whapi_mark_read(self):
        for chat in self.filtered('unread_count'):
            unread = chat.message_ids.filtered(lambda m: m.direction == 'in' and m.state == 'received')
            last = unread.sorted('id')[-1:]
            if last and not last.wa_id.startswith('sandbox-'):
                try:
                    chat.account_id._whapi_request('PUT', f'/messages/{last.wa_id}')
                except UserError:
                    pass
            chat.sudo().unread_count = 0
        return True

    def whapi_send(self, body='', attachments=None, reply_to_id=False, voice=False):
        """Send from the chat screen. ``attachments``: [{'name', 'mimetype', 'data' (base64)}]."""
        self.ensure_one()
        Attachment = self.env['ir.attachment']
        records = Attachment
        for item in attachments or []:
            records |= Attachment.create({'name': item.get('name') or 'file',
                                          'raw': base64.b64decode(item.get('data') or ''),
                                          'mimetype': item.get('mimetype'), 'res_model': 'whapi.chat',
                                          'res_id': self.id})
        messages = self.env['whapi.message']._whapi_send_to_chat(
            self, body=body, attachments=records, reply_to=self.env['whapi.message'].browse(reply_to_id or []),
            voice=voice)
        return [m._whapi_message_dict() for m in messages]

    def whapi_render_templates(self):
        """Contact templates, rendered for the contact of this chat (composer shortcut)."""
        self.ensure_one()
        templates = self.env['whapi.template'].search([('model', '=', 'res.partner')])
        partner = self.partner_id
        result = []
        for template in templates:
            body = template._whapi_render_body(partner.ids).get(partner.id) if partner else template.body
            result.append({'id': template.id, 'name': template.name, 'body': body or ''})
        return result

    def whapi_group_info(self):
        self.ensure_one()
        media = self.message_ids.filtered(lambda m: m.attachment_ids and m.state != 'deleted').sorted('id',
                                                                                                      reverse=True)
        starred = self.message_ids.filtered('starred').sorted('id', reverse=True)
        return {
            'chat': self._whapi_chat_dict(),
            'description': self.description or '',
            'participants': [{'id': p.id, 'name': p.name or ('+' + p.wa_id), 'phone': '+' + p.wa_id,
                              'rank': p.rank, 'partner_id': p.partner_id.id}
                             for p in self.participant_ids.sorted(lambda p: (p.rank == 'member', p.name or ''))],
            'events': [{'id': e.id, 'kind': e.kind, 'label': e._label(),
                        'date': fields.Datetime.to_string(e.date)} for e in self.event_ids[:30]],
            'media': [a._whapi_attachment_dict() for m in media[:30] for a in m.attachment_ids][:30],
            'starred': [m._whapi_message_dict() for m in starred[:30]],
        }

    def _whapi_notify(self, payload):
        """Tell the open chat screens of the allowed users that something changed."""
        for chat in self:
            account = chat.account_id
            users = account.user_ids or self.env.ref('whatsapp_whapi.group_whapi_user').all_user_ids
            users = users.filtered(lambda u: not u.share and account.company_id in u.company_ids)
            for user in users:
                user.partner_id._bus_send('whapi/update', dict(payload, chat_id=chat.id,
                                                                  account_id=account.id,
                                                                  notify=account.notify))


class WhapiChatParticipant(models.Model):
    _name = 'whapi.chat.participant'
    _description = 'WhatsApp group participant'
    _order = 'rank desc, name, id'

    chat_id = fields.Many2one('whapi.chat', required=True, ondelete='cascade', index=True)
    wa_id = fields.Char('Phone', required=True)
    name = fields.Char()
    partner_id = fields.Many2one('res.partner', string='Contact')
    rank = fields.Selection([('member', 'Member'), ('admin', 'Admin'), ('creator', 'Creator')], default='member',
                            required=True)


class WhapiChatEvent(models.Model):
    _name = 'whapi.chat.event'
    _description = 'WhatsApp group event'
    _order = 'date desc, id desc'

    chat_id = fields.Many2one('whapi.chat', required=True, ondelete='cascade', index=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    kind = fields.Selection([('join', 'Joined'), ('leave', 'Left'), ('promote', 'Made admin'),
                             ('demote', 'Admin removed'), ('created', 'Group created'),
                             ('subject', 'Name changed')], required=True)
    participant = fields.Char()
    author = fields.Char()

    def _label(self):
        self.ensure_one()
        chat = self.chat_id
        names = {p.wa_id: p.name for p in chat.participant_ids if p.name}

        def who(number):
            return names.get(number) or (f'+{number}' if number else '')

        verb = dict(self._fields['kind'].selection)[self.kind]
        text = f'{who(self.participant)} · {verb}' if self.participant else verb
        if self.author and self.author != self.participant:
            text += self.env._(' (by %s)', who(self.author))
        return text
