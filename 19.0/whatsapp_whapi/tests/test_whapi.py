import base64
import json
from contextlib import contextmanager
from unittest.mock import patch

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.whatsapp_whapi.models.whapi_account import WhapiAccount

PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')


class FakeWhapi:
    """Records the API calls and answers like Whapi.Cloud."""

    def __init__(self):
        self.calls = []
        self.counter = 0
        self.fail = False

    def __call__(self, account, method, path, payload=None, params=None, raw=False):
        self.calls.append((method, path, payload, params))
        if self.fail:
            raise UserError('WhatsApp gateway error 500: boom')
        if method == 'POST' and path.startswith('/messages'):
            self.counter += 1
            return {'sent': True, 'message': {'id': f'WA{self.counter:04d}'}}
        if path == '/health':
            return {'status': {'code': 4, 'text': 'AUTH'}, 'user': {'id': '32470000000', 'name': 'Brightwave'}}
        if path == '/users/login':
            return {'base64': 'data:image/png;base64,' + base64.b64encode(PNG).decode()}
        if path.startswith('/media/'):
            return PNG
        if path == '/chats':
            return {'chats': [{'id': '32471111111@s.whatsapp.net', 'name': 'Anna Peeters', 'unread': 2,
                               'timestamp': 1761900000},
                              {'id': '120363000000000001@g.us', 'name': 'Installers', 'timestamp': 1761900100},
                              {'id': 'status@broadcast'}]}
        if path == '/groups':
            return {'groups': [{'id': '120363000000000001@g.us', 'name': 'Installers',
                                'participants': [{'id': '32470000000', 'rank': 'creator'},
                                                 {'id': '32472222222', 'rank': 'admin'},
                                                 {'id': '32473333333', 'rank': 'member'}]}]}
        return {}

    def paths(self):
        return [path for _method, path, _payload, _params in self.calls]


@tagged('post_install', '-at_install')
class TestWhapi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account = cls.env['whapi.account'].create({'name': 'Sales WhatsApp', 'token': 'secret-token',
                                                       'phone': '32470000000'})
        cls.partner = cls.env['res.partner'].create({'name': 'Anna Peeters', 'phone': '+32 471 11 11 11'})
        cls.user = new_test_user(cls.env, 'agent', groups='base.group_user,whatsapp_whapi.group_whapi_user',
                                 name='Wendy Agent')
        cls.outsider = new_test_user(cls.env, 'outsider', groups='base.group_user', name='No WhatsApp')

    @contextmanager
    def fake(self):
        fake = FakeWhapi()
        with patch.object(WhapiAccount, '_whapi_request', lambda self, *a, **k: fake(self, *a, **k)):
            yield fake

    def webhook(self, payload, account=None, secret=None):
        account = account or self.account
        return self.url_open(f'/whapi/webhook/{account.id}/{secret or account.webhook_secret}',
                             data=json.dumps(payload), headers={'Content-Type': 'application/json'})

    def incoming(self, text='Hello, is my order ready?', msg_id='IN001', chat='32471111111@s.whatsapp.net', **extra):
        message = {'id': msg_id, 'from_me': False, 'type': 'text', 'chat_id': chat, 'timestamp': 1761900200,
                   'from': chat.split('@')[0], 'from_name': 'Anna', 'text': {'body': text}}
        message.update(extra)
        return {'messages': [message], 'event': {'type': 'messages', 'event': 'post'}}

    # ------------------------------------------------------------------
    def test_connection_qr_webhook_and_sync(self):
        with self.fake() as fake:
            self.account.action_check_connection()
            self.assertEqual(self.account.state, 'connected')
            self.assertEqual(self.account.wa_name, 'Brightwave')
            self.account.action_get_qr()
            self.assertTrue(self.account.qr_code)
            self.account.action_set_webhook()
            method, path, payload, _params = fake.calls[-1]
            self.assertEqual((method, path), ('PATCH', '/settings'))
            self.assertTrue(payload['webhooks'][0]['url'].endswith(
                f'/whapi/webhook/{self.account.id}/{self.account.webhook_secret}'))
            self.account.action_sync()
        chats = self.account.chat_ids
        self.assertEqual(len(chats), 2, 'the broadcast chat is skipped')
        anna = chats.filtered(lambda c: c.chat_type == 'contact')
        self.assertEqual(anna.partner_id, self.partner, 'matched on the phone number')
        self.assertEqual(anna.unread_count, 2)
        group = chats.filtered(lambda c: c.chat_type == 'group')
        self.assertEqual(sorted(group.participant_ids.mapped('rank')), ['admin', 'creator', 'member'])

    def test_send_text_and_media(self):
        chat = self.partner._whapi_get_chat(self.account)
        self.assertEqual(chat.wa_id, '32471111111@s.whatsapp.net')
        with self.fake() as fake:
            [text] = chat.with_user(self.user).whapi_send('Your order ships today 🚚')
            self.assertEqual(fake.calls[-1][1], '/messages/text')
            self.assertEqual(fake.calls[-1][2], {'to': chat.wa_id, 'body': 'Your order ships today 🚚'})
            sent = chat.with_user(self.user).whapi_send('Two pictures', attachments=[
                {'name': 'a.png', 'mimetype': 'image/png', 'data': base64.b64encode(PNG).decode()},
                {'name': 'quote.pdf', 'mimetype': 'application/pdf', 'data': base64.b64encode(b'%PDF-1.4').decode()},
            ], reply_to_id=text['id'])
        self.assertEqual(len(sent), 2)
        (_m1, image_path, image_payload, _p1), (_m2, doc_path, doc_payload, _p2) = fake.calls[-2:]
        self.assertEqual(image_path, '/messages/image')
        self.assertEqual(image_payload['caption'], 'Two pictures')
        self.assertEqual(image_payload['quoted'], 'WA0001')
        self.assertTrue(image_payload['media'].startswith('data:image/png;name=a.png;base64,'))
        self.assertEqual(doc_path, '/messages/document')
        self.assertEqual(doc_payload['filename'], 'quote.pdf')
        self.assertNotIn('caption', doc_payload)
        messages = chat.message_ids.sorted('id')
        self.assertEqual(messages.mapped('state'), ['sent'] * 3)
        self.assertEqual(messages.mapped('wa_id'), ['WA0001', 'WA0002', 'WA0003'])
        self.assertEqual(messages[1].attachment_ids.res_model, 'whapi.message')
        self.assertEqual(messages[0].user_id, self.user)
        self.assertTrue(chat.last_message_preview.startswith('✓ '))
        # copied in the contact's chatter
        self.assertIn('Your order ships today', self.partner.message_ids[:3].mapped('body')[-1])

    def test_failed_send_and_retry(self):
        chat = self.partner._whapi_get_chat(self.account)
        with self.fake() as fake:
            fake.fail = True
            [message] = chat.whapi_send('Hello')
            message = self.env['whapi.message'].browse(message['id'])
            self.assertEqual(message.state, 'failed')
            self.assertIn('boom', message.error)
            fake.fail = False
            message.action_retry()
        self.assertEqual(message.state, 'sent')
        self.assertFalse(message.error)

    def test_webhook_incoming_text_media_reply_and_security(self):
        self.assertEqual(self.webhook(self.incoming(), secret='wrong').status_code, 403)
        self.assertFalse(self.account.chat_ids)
        with self.fake():
            response = self.webhook(self.incoming())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['messages'], 1)
            # the same message twice is ignored
            self.assertEqual(self.webhook(self.incoming()).json()['messages'], 1)
            image = self.incoming(msg_id='IN002', type='image',
                                  image={'id': 'media-1', 'mime_type': 'image/png', 'caption': 'The broken part'},
                                  context={'quoted_id': 'IN001'})
            image['messages'][0].pop('text')
            self.webhook(image)
        chat = self.account.chat_ids
        self.assertEqual(chat.partner_id, self.partner)
        self.assertEqual(chat.unread_count, 2)
        first, second = chat.message_ids.sorted('id')
        self.assertEqual((first.direction, first.state, first.body), ('in', 'received', 'Hello, is my order ready?'))
        self.assertEqual(second.msg_type, 'image')
        self.assertEqual(second.body, 'The broken part')
        self.assertEqual(second.reply_to_id, first)
        self.assertEqual(bytes(second.attachment_ids.raw), PNG)
        self.assertEqual(second.attachment_ids.mimetype, 'image/png')
        with self.fake() as fake:
            chat.with_user(self.user).whapi_mark_read()
        self.assertEqual(chat.unread_count, 0)
        self.assertEqual(fake.calls[-1][:2], ('PUT', '/messages/IN002'))

    def test_webhook_statuses_delete_edit_and_phone_echo(self):
        chat = self.partner._whapi_get_chat(self.account)
        with self.fake():
            [sent] = chat.whapi_send('Price: 120 EUR')
        message = self.env['whapi.message'].browse(sent['id'])
        self.webhook({'statuses': [{'id': message.wa_id, 'status': 'delivered', 'recipient_id': '32471111111',
                                    'timestamp': 1761900300}]})
        self.assertEqual(message.state, 'delivered')
        self.webhook({'statuses': [{'id': message.wa_id, 'status': 'read', 'recipient_id': '32471111111'}]})
        self.assertEqual(message.state, 'read')
        # an older status never goes back
        self.webhook({'statuses': [{'id': message.wa_id, 'status': 'delivered'}]})
        self.assertEqual(message.state, 'read')
        self.assertEqual(message.status_ids.status, 'read')
        # edited then deleted by the customer
        with self.fake():
            self.webhook(self.incoming('Can you do 100?', msg_id='IN010'))
        incoming = chat.message_ids.filtered(lambda m: m.wa_id == 'IN010')
        self.webhook({'messages': [{'id': 'ACT1', 'type': 'action', 'chat_id': chat.wa_id,
                                    'action': {'type': 'edit', 'target': 'IN010',
                                               'edited_content': {'body': 'Can you do 110?'}}}]})
        self.assertEqual(incoming.body, 'Can you do 110?')
        self.webhook({'messages': [{'id': 'ACT2', 'type': 'action', 'chat_id': chat.wa_id,
                                    'action': {'type': 'delete', 'target': 'IN010'}}]})
        self.assertEqual(incoming.state, 'deleted')
        self.assertEqual(incoming._whapi_message_dict()['body'], '')
        # sent from the phone itself
        with self.fake():
            self.webhook(self.incoming('Sent from my phone', msg_id='OUT77', from_me=True))
        echo = chat.message_ids.filtered(lambda m: m.wa_id == 'OUT77')
        self.assertEqual((echo.direction, echo.state), ('out', 'sent'))

    def test_groups_events_receipts_and_admin_actions(self):
        with self.fake():
            self.account.action_sync()
        group = self.account.chat_ids.filtered(lambda c: c.chat_type == 'group')
        with self.fake() as fake:
            [sent] = group.whapi_send('Meeting at 8:00 on site')
            message = self.env['whapi.message'].browse(sent['id'])
            self.webhook({'statuses': [{'id': message.wa_id, 'status': 'read', 'viewer_id': '32472222222'}]})
            self.assertEqual(message.state, 'delivered', 'one of two participants has read it')
            info = message.whapi_info()
            self.assertEqual([s['status'] for s in info['statuses']], ['read'])
            self.assertEqual(len(info['pending']), 1)
            self.webhook({'statuses': [{'id': message.wa_id, 'status': 'read', 'viewer_id': '32473333333'}]})
            self.assertEqual(message.state, 'read')
            # members join / are promoted through webhooks
            self.webhook({'groups_participants': [{'group_id': group.wa_id, 'participants': ['32474444444'],
                                                   'action': 'add', 'author': '32472222222'}]})
            self.assertIn('32474444444', group.participant_ids.mapped('wa_id'))
            newcomer = group.participant_ids.filtered(lambda p: p.wa_id == '32474444444')
            group.whapi_set_admin(newcomer.id, True)
            self.assertEqual(fake.calls[-1][:2], ('PATCH', f'/groups/{group.wa_id}/admins'))
            self.assertEqual(newcomer.rank, 'admin')
            group.whapi_set_admin(newcomer.id, False)
            self.assertEqual(newcomer.rank, 'member')
            group.whapi_add_participants(['+32 475 55 55 55'])
            self.assertEqual(fake.calls[-1][2], {'participants': ['32475555555']})
            group.whapi_remove_participant(newcomer.id)
        self.assertNotIn('32474444444', group.participant_ids.mapped('wa_id'))
        info = group.whapi_group_info()
        self.assertEqual([e['kind'] for e in info['events']][:5], ['leave', 'join', 'demote', 'promote', 'join'])
        self.assertIn('(by', info['events'][-1]['label'])
        # incoming group message: author name from the payload
        with self.fake():
            self.webhook(self.incoming('On my way', msg_id='G1', chat=group.wa_id, **{'from': '32473333333',
                                                                                        'from_name': 'Tom'}))
        self.assertEqual(group.message_ids.filtered(lambda m: m.wa_id == 'G1').author_name, 'Tom')

    def test_forward_star_delete_and_blocked_chat(self):
        anna = self.partner._whapi_get_chat(self.account)
        other = self.env['res.partner'].create({'name': 'Bob', 'phone': '+32 476 66 66 66'})._whapi_get_chat(
            self.account)
        third = self.env['res.partner'].create({'name': 'Carl', 'phone': '0032477777777'})._whapi_get_chat(
            self.account)
        self.assertEqual(third.wa_id, '32477777777@s.whatsapp.net', '00 prefix removed')
        belgian = self.env['res.partner'].create({'name': 'Dirk', 'phone': '0478 88 88 88',
                                                  'country_id': self.env.ref('base.be').id})
        self.assertEqual(belgian._whapi_get_chat(self.account).wa_id, '32478888888@s.whatsapp.net',
                         'national number completed with the country code')
        with self.fake() as fake:
            [sent] = anna.whapi_send('Catalogue 2027')
            message = self.env['whapi.message'].browse(sent['id'])
            self.assertEqual(message.whapi_forward([other.id, third.id]), 2)
            self.assertEqual(fake.paths()[-2:], [f'/messages/{message.wa_id}'] * 2)
            self.assertTrue(other.message_ids.forwarded)
            self.assertTrue(message.whapi_toggle_star())
            self.assertIn(message.id, [m['id'] for m in anna.whapi_group_info()['starred']])
            message.whapi_delete()
            self.assertEqual(fake.calls[-1][:2], ('DELETE', f'/messages/{message.wa_id}'))
        self.assertEqual(message.state, 'deleted')
        self.assertFalse(message.starred)
        anna.blocked = True
        with self.fake():
            self.webhook(self.incoming('spam', msg_id='SPAM'))
        self.assertFalse(anna.message_ids.filtered(lambda m: m.wa_id == 'SPAM'))
        with self.assertRaises(UserError):
            anna.whapi_send('blocked')

    def test_sandbox_account(self):
        sandbox = self.env['whapi.account'].create({'name': 'Staging', 'sandbox': True})
        chat = self.partner._whapi_get_chat(sandbox)
        [sent] = chat.whapi_send('Test from staging')
        message = self.env['whapi.message'].browse(sent['id'])
        self.assertEqual(message.state, 'sent')
        self.assertTrue(message.wa_id.startswith('sandbox-'))
        sandbox.action_check_connection()
        self.assertEqual(sandbox.state, 'connected')

    def test_templates_composer_and_binding(self):
        template = self.env['whapi.template'].create({
            'name': 'Welcome', 'body': 'Hello {{ object.name }}, welcome at {{ object.company_id.name or "us" }}!',
            'model_id': self.env['ir.model']._get('res.partner').id,
            'report_id': False,
        })
        template.action_add_binding()
        self.assertEqual(template.binding_action_id.binding_model_id.model, 'res.partner')
        bob = self.env['res.partner'].create({'name': 'Bob', 'phone': '+32 476 66 66 66'})
        nophone = self.env['res.partner'].create({'name': 'No phone'})
        composer = self.env['whapi.composer'].with_context(
            active_model='res.partner', active_ids=[self.partner.id, bob.id, nophone.id],
            default_template_id=template.id).create({'account_id': self.account.id})
        self.assertEqual(composer.body, 'Hello Anna Peeters, welcome at us!')
        self.assertIn('no phone number', composer.recipient_summary)
        with self.fake():
            result = composer.action_send()
        self.assertIn('No phone number for: No phone', result['params']['message'])
        bodies = self.env['whapi.message'].search([('res_model', '=', 'res.partner')]).mapped('body')
        self.assertEqual(sorted(bodies), ['Hello Anna Peeters, welcome at us!', 'Hello Bob, welcome at us!'])
        chat = self.partner._whapi_get_chat(self.account)
        self.assertEqual(chat.whapi_render_templates()[0]['body'], 'Hello Anna Peeters, welcome at us!')
        template.unlink()
        self.assertFalse(self.env['ir.actions.act_window'].search([('res_model', '=', 'whapi.composer'),
                                                                   ('binding_model_id.model', '=', 'res.partner')]))

    def test_composer_from_record_attaches_report(self):
        report = self.env['ir.actions.report'].search([('model', '=', 'res.partner'),
                                                       ('report_type', '=', 'qweb-pdf')], limit=1)
        if not report:
            self.skipTest('no partner PDF report in this database')
        template = self.env['whapi.template'].create({
            'name': 'Doc', 'body': 'Here is your document', 'report_id': report.id,
            'model_id': self.env['ir.model']._get('res.partner').id})
        composer = self.env['whapi.composer'].with_context(
            active_model='res.partner', active_ids=self.partner.ids).create(
            {'account_id': self.account.id, 'template_id': template.id})
        self.assertTrue(composer.attach_report)
        with self.fake() as fake, patch.object(type(self.env['ir.actions.report']), '_render',
                                               lambda *a, **k: (b'%PDF-1.4 fake', 'pdf')):
            composer.action_send()
        self.assertEqual(fake.calls[-1][1], '/messages/document')

    def test_access_rules(self):
        private = self.env['whapi.account'].create({'name': 'Management', 'user_ids': [(6, 0, self.env.ref(
            'base.user_admin').ids)]})
        self.partner._whapi_get_chat(private)
        self.partner._whapi_get_chat(self.account)
        Chat = self.env['whapi.chat'].with_user(self.user)
        visible = Chat.whapi_load_chats()
        self.assertEqual([a['name'] for a in visible['accounts']], ['Sales WhatsApp'])
        self.assertEqual(len(visible['chats']), 1)
        self.assertNotIn('token', self.env['whapi.account'].with_user(self.user).fields_get())
        with self.assertRaises(AccessError):
            self.env['whapi.chat'].with_user(self.outsider).search([])
        self.assertEqual(self.partner.with_user(self.user).action_whapi_open_chat()['tag'], 'whatsapp_whapi.chat')

    def test_ui_data(self):
        chat = self.partner._whapi_get_chat(self.account)
        with self.fake():
            for index in range(5):
                chat.whapi_send(f'message {index}')
        data = chat.whapi_load_messages(limit=3)
        self.assertEqual([m['body'] for m in data['messages']], ['message 2', 'message 3', 'message 4'])
        self.assertTrue(data['more'])
        older = chat.whapi_load_messages(before_id=data['messages'][0]['id'], limit=3)
        self.assertEqual([m['body'] for m in older['messages']], ['message 0', 'message 1'])
        self.assertEqual(self.env['whapi.chat'].whapi_load_chats(search='Anna')['chats'][0]['id'], chat.id)
        self.assertFalse(self.env['whapi.chat'].whapi_load_chats(mode='unread')['chats'])

    def test_tour(self):
        self.partner._whapi_get_chat(self.account)
        self.env['whapi.account'].browse(self.account.id).sandbox = True
        with self.fake():
            self.webhook(self.incoming('Hi! Do you deliver on Saturday?', msg_id='T1'))
        self.start_tour('/odoo/whatsapp', 'whatsapp_whapi_tour', login='admin')
        chat = self.account.chat_ids
        bodies = chat.message_ids.sorted('id').mapped('body')
        self.assertEqual(bodies[-1], 'Yes, from 9 to 12.')
        self.assertTrue(chat.message_ids.filtered(lambda m: m.body == 'Yes, from 9 to 12.').reply_to_id)
