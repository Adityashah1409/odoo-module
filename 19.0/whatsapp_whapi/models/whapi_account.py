import base64
import logging
import re
import secrets
import uuid
from datetime import UTC, datetime

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIMEOUT = 30
WEBHOOK_EVENTS = ['messages', 'statuses', 'groups', 'chats']


def digits(value):
    return re.sub(r'\D', '', value or '')


def ts_to_datetime(timestamp):
    try:
        return datetime.fromtimestamp(int(timestamp), tz=UTC).replace(tzinfo=None)
    except (TypeError, ValueError, OverflowError):
        return False


def normalize_phone(phone, country_code=None):
    """International digits of a phone number: +32 470.., 0032 470.. or (with the country code) 0470..."""
    number = digits(phone)
    if not number:
        return ''
    if (phone or '').strip().startswith('+'):
        return number
    if number.startswith('00'):
        return number[2:]
    if number.startswith('0') and country_code:
        return f'{country_code}{number[1:]}'
    return number


def chat_id_for_phone(phone, country_code=None):
    """Whapi chat id of a phone number."""
    number = normalize_phone(phone, country_code)
    return f'{number}@s.whatsapp.net' if number else False


class WhapiError(UserError):
    pass


class WhapiAccount(models.Model):
    _name = 'whapi.account'
    _description = 'WhatsApp account (Whapi.Cloud channel)'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    api_url = fields.Char('API URL', required=True, default='https://gate.whapi.cloud', tracking=True)
    token = fields.Char('API token', groups='whatsapp_whapi.group_whapi_manager', copy=False,
                        help='Token of the channel, from the Whapi.Cloud dashboard.')
    sandbox = fields.Boolean('Sandbox', tracking=True,
                             help='Nothing is sent to WhatsApp: messages are marked as sent locally. Use it on '
                                  'development and staging databases.')
    state = fields.Selection([('new', 'Not checked'), ('connected', 'Connected'), ('qr', 'Waiting for QR scan'),
                              ('error', 'Error')], default='new', required=True, readonly=True, tracking=True)
    status_text = fields.Char('Status', readonly=True)
    last_check = fields.Datetime(readonly=True)
    phone = fields.Char('WhatsApp number', readonly=True)
    wa_name = fields.Char('WhatsApp name', readonly=True)
    qr_code = fields.Binary('QR code', readonly=True, attachment=False)
    webhook_secret = fields.Char(copy=False, groups='whatsapp_whapi.group_whapi_manager',
                                 default=lambda self: secrets.token_urlsafe(24))
    webhook_url = fields.Char(compute='_compute_webhook_url', groups='whatsapp_whapi.group_whapi_manager')
    user_ids = fields.Many2many('res.users', string='Allowed users',
                                domain=[('share', '=', False)],
                                help='Users who can chat with this account. Empty = every WhatsApp user.')
    sync_groups = fields.Boolean('Groups', default=True, help='Show WhatsApp groups in the inbox.')
    log_in_chatter = fields.Boolean('Log in contact chatter', default=True,
                                    help='Copy every message in the chatter of the matching contact.')
    notify = fields.Boolean('Browser notifications', default=True,
                            help='Pop a notification in Odoo for new incoming messages.')
    chat_ids = fields.One2many('whapi.chat', 'account_id')
    chat_count = fields.Integer(compute='_compute_counts')
    message_count = fields.Integer(compute='_compute_counts')

    @api.depends('webhook_secret')
    def _compute_webhook_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for account in self:
            account.webhook_url = (f'{base}/whapi/webhook/{account.id}/{account.webhook_secret}'
                                   if account.id and account.webhook_secret else False)

    def _compute_counts(self):
        chats = dict(self.env['whapi.chat']._read_group([('account_id', 'in', self.ids)], ['account_id'],
                                                        ['__count']))
        messages = dict(self.env['whapi.message']._read_group([('account_id', 'in', self.ids)], ['account_id'],
                                                              ['__count']))
        for account in self:
            account.chat_count = chats.get(account, 0)
            account.message_count = messages.get(account, 0)

    # ------------------------------------------------------------------
    # transport
    # ------------------------------------------------------------------
    def _whapi_request(self, method, path, payload=None, params=None, raw=False):
        """Call the Whapi.Cloud API. Returns the decoded JSON (or bytes with ``raw``)."""
        self.ensure_one()
        if self.sandbox:
            return self._whapi_sandbox_response(method, path, payload)
        account = self.sudo()
        if not account.token:
            raise WhapiError(self.env._('Set the API token of %s first.', self.name))
        url = account.api_url.rstrip('/') + '/' + path.lstrip('/')
        headers = {'Authorization': f'Bearer {account.token}', 'Accept': '*/*' if raw else 'application/json'}
        try:
            response = requests.request(method, url, json=payload, params=params, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as error:
            _logger.warning('Whapi %s %s failed: %s', method, path, error)
            raise WhapiError(self.env._('WhatsApp gateway unreachable: %s', error)) from error
        if response.status_code >= 400:
            try:
                detail = response.json().get('error', {})
                message = detail.get('message') or detail.get('details') or response.text
            except ValueError:
                message = response.text
            _logger.info('Whapi %s %s -> %s %s', method, path, response.status_code, message)
            raise WhapiError(self.env._('WhatsApp gateway error %(code)s: %(message)s',
                                        code=response.status_code, message=(message or '')[:300]))
        if raw:
            return response.content
        try:
            return response.json() if response.content else {}
        except ValueError:
            return {}

    def _whapi_sandbox_response(self, method, path, payload):
        if path.startswith('/messages') and method == 'POST':
            return {'sent': True, 'message': {'id': f'sandbox-{uuid.uuid4().hex[:16]}', 'status': 'sent'}}
        if path == '/health':
            return {'status': {'code': 4, 'text': 'AUTH'}, 'user': {'id': '15550000000', 'name': 'Sandbox'}}
        if path.startswith('/media/'):
            return b''
        return {}

    # ------------------------------------------------------------------
    # account actions
    # ------------------------------------------------------------------
    def action_check_connection(self):
        for account in self:
            try:
                result = account._whapi_request('GET', '/health')
            except WhapiError as error:
                account.write({'state': 'error', 'status_text': str(error)[:200], 'last_check': fields.Datetime.now()})
                continue
            status = (result.get('status') or {}).get('text', '')
            user = result.get('user') or {}
            account.write({
                'state': 'connected' if status == 'AUTH' else 'qr' if status in ('QR', 'INIT', 'LAUNCH') else 'error',
                'status_text': status or 'unknown',
                'phone': user.get('id') or account.phone,
                'wa_name': user.get('name') or user.get('pushname') or account.wa_name,
                'last_check': fields.Datetime.now(),
            })
        return self._notify_result(self.env._('Connection checked: %s', ', '.join(self.mapped('status_text'))))

    def action_get_qr(self):
        self.ensure_one()
        result = self._whapi_request('GET', '/users/login', params={'wakeup': 'true'})
        image = result.get('base64') or ''
        if not image:
            self.action_check_connection()
            return self._notify_result(self.env._('No QR code: the phone is probably already linked.'))
        self.write({'qr_code': image.split(',', 1)[-1], 'state': 'qr', 'status_text': 'QR'})
        return True

    def action_set_webhook(self):
        for account in self:
            account._whapi_request('PATCH', '/settings', {
                'webhooks': [{'url': account.sudo().webhook_url, 'mode': 'body',
                              'events': [{'type': t, 'method': 'post'} for t in WEBHOOK_EVENTS]
                              + [{'type': 'messages', 'method': 'patch'}, {'type': 'groups', 'method': 'patch'}]}],
            })
        return self._notify_result(self.env._('Webhook registered on Whapi.Cloud.'))

    def action_regenerate_secret(self):
        for account in self:
            account.sudo().webhook_secret = secrets.token_urlsafe(24)

    def action_sync(self):
        for account in self:
            account._whapi_sync_chats()
        return self._notify_result(self.env._('Chats synchronised.'))

    def action_open_chat(self):
        return {'type': 'ir.actions.client', 'tag': 'whatsapp_whapi.chat', 'params': {'account_id': self.id}}

    def action_view_messages(self):
        action = self.env['ir.actions.act_window']._for_xml_id('whatsapp_whapi.action_whapi_message')
        action['domain'] = [('account_id', '=', self.id)]
        return action

    def _notify_result(self, message):
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': message, 'type': 'info', 'next': {'type': 'ir.actions.client',
                                                                         'tag': 'soft_reload'}}}

    # ------------------------------------------------------------------
    # chats
    # ------------------------------------------------------------------
    def _whapi_get_chat(self, wa_id, name=None, partner=None):
        """Chat of this account for ``wa_id``, created when missing."""
        self.ensure_one()
        Chat = self.env['whapi.chat'].sudo()
        chat = Chat.with_context(active_test=False).search([('account_id', '=', self.id), ('wa_id', '=', wa_id)],
                                                           limit=1)
        if not chat:
            is_group = wa_id.endswith('@g.us')
            partner = partner or (not is_group and Chat._whapi_find_partner(wa_id.split('@')[0]))
            chat = Chat.create({
                'account_id': self.id, 'wa_id': wa_id, 'chat_type': 'group' if is_group else 'contact',
                'name': name or (partner and partner.name) or ('+' + wa_id.split('@')[0]),
                'partner_id': partner and partner.id,
            })
        return chat

    def _whapi_sync_chats(self):
        self.ensure_one()
        result = self._whapi_request('GET', '/chats', params={'count': 200})
        for item in result.get('chats', []):
            wa_id = item.get('id') or ''
            if not wa_id or (wa_id.endswith('@g.us') and not self.sync_groups) or wa_id.endswith('@broadcast'):
                continue
            chat = self._whapi_get_chat(wa_id, item.get('name'))
            values = {'unread_count': item.get('unread') or 0}
            if item.get('name') and chat.name.startswith('+'):
                values['name'] = item['name']
            if item.get('timestamp') and not chat.last_message_at:
                values['last_message_at'] = ts_to_datetime(item['timestamp'])
            chat.write(values)
        if self.sync_groups:
            groups = self._whapi_request('GET', '/groups', params={'count': 200})
            for item in groups.get('groups', []):
                chat = self._whapi_get_chat(item['id'], item.get('name'))
                chat._whapi_set_participants(item.get('participants') or [])

    # ------------------------------------------------------------------
    # incoming webhooks
    # ------------------------------------------------------------------
    def _whapi_process_webhook(self, payload):
        self.ensure_one()
        result = {'messages': 0, 'statuses': 0, 'groups': 0}
        Message = self.env['whapi.message'].sudo()
        for data in payload.get('messages') or []:
            if Message._whapi_from_webhook(self, data):
                result['messages'] += 1
        for data in payload.get('statuses') or []:
            if Message._whapi_status_from_webhook(self, data):
                result['statuses'] += 1
        for data in payload.get('groups_participants') or []:
            chat = self._whapi_get_chat(data.get('group_id') or '')
            chat._whapi_participants_event(data)
            result['groups'] += 1
        for data in payload.get('groups') or []:
            if data.get('id'):
                chat = self._whapi_get_chat(data['id'], data.get('name'))
                if data.get('name') and data['name'] != chat.name:
                    chat.name = data['name']
                if data.get('participants'):
                    chat._whapi_set_participants(data['participants'])
                result['groups'] += 1
        return result

    @api.model
    def _cron_check_connections(self):
        self.search([('sandbox', '=', False)]).action_check_connection()

    @api.model
    def _whapi_media_data_url(self, attachment):
        name = (attachment.name or 'file').replace(';', '_')
        return f'data:{attachment.mimetype or "application/octet-stream"};name={name};base64,' + \
            base64.b64encode(bytes(attachment.raw or b'')).decode()
