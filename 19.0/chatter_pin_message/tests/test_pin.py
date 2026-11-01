import ast

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


class PinCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, 'pin_user', groups='base.group_user,base.group_partner_manager',
                                 name='Paula Pinner')
        cls.partner = cls.env['res.partner'].create({'name': 'Harbour Logistics'})
        cls.other = cls.env['res.partner'].create({'name': 'Other partner'})
        cls.note = cls.partner.message_post(body='Delivery window: Tuesdays 8-10 only', message_type='comment',
                                            subtype_xmlid='mail.mt_note')
        cls.msg = cls.partner.message_post(body='Contract renewed until 2027', message_type='comment',
                                           subtype_xmlid='mail.mt_comment')
        cls.tracking = cls.partner._message_log(body='Stage changed')
        cls.icp = cls.env['ir.config_parameter'].sudo()
        cls.icp.set_param('chatter_pin_message.max', 5)
        cls.icp.set_param('chatter_pin_message.access', 'write')


class TestPin(PinCommon):

    def test_pin_and_unpin(self):
        write_date = self.note.write_date
        res = self.partner.with_user(self.user).chatter_set_message_pin(self.note.id, True)
        self.note.invalidate_recordset()
        self.assertTrue(self.note.pinned_at)
        self.assertEqual(self.note.pinned_by_id, self.user)
        self.assertEqual(self.note.write_date, write_date, 'pinning does not change the message')
        self.assertEqual(res['pinned_by'][self.note.id]['name'], 'Paula Pinner')
        self.assertIn('mail.message', res['store'])
        data = self.partner.with_user(self.user).chatter_pinned_messages()
        self.assertEqual(list(data['pinned_by']), [self.note.id])
        # pin twice is harmless
        self.partner.chatter_set_message_pin(self.note.id, True)
        self.partner.with_user(self.user).chatter_set_message_pin(self.note.id, False)
        self.note.invalidate_recordset()
        self.assertFalse(self.note.pinned_at)
        self.assertFalse(self.note.pinned_by_id)

    def test_wrong_messages(self):
        with self.assertRaises(UserError):
            self.other.chatter_set_message_pin(self.note.id, True)
        with self.assertRaises(UserError):
            self.partner.chatter_set_message_pin(self.tracking.id, True)

    def test_limit(self):
        self.icp.set_param('chatter_pin_message.max', 1)
        self.partner.chatter_set_message_pin(self.note.id, True)
        with self.assertRaises(UserError):
            self.partner.chatter_set_message_pin(self.msg.id, True)
        self.icp.set_param('chatter_pin_message.max', 0)
        self.partner.chatter_set_message_pin(self.msg.id, True)
        self.assertEqual(len(self.partner.chatter_pinned_messages()['pinned_by']), 2)

    def test_access(self):
        group = self.env['res.groups'].create({'name': 'Read-only partner test'})
        self.user.group_ids = [Command.link(group.id)]
        self.env['ir.rule'].create({
            'name': 'no write on Harbour', 'model_id': self.env.ref('base.model_res_partner').id,
            'domain_force': [('id', '!=', self.partner.id)], 'groups': [Command.link(group.id)],
            'perm_read': False, 'perm_create': False, 'perm_unlink': False, 'perm_write': True,
        })
        with self.assertRaises(AccessError):
            self.partner.with_user(self.user).chatter_set_message_pin(self.note.id, True)
        self.icp.set_param('chatter_pin_message.access', 'read')
        self.partner.with_user(self.user).chatter_set_message_pin(self.note.id, True)
        self.assertTrue(self.note.pinned_at)
        portal = new_test_user(self.env, 'pin_portal', groups='base.group_portal')
        with self.assertRaises(AccessError):
            self.partner.with_user(portal).chatter_set_message_pin(self.msg.id, True)

    def test_overview(self):
        self.partner.chatter_set_message_pin(self.note.id, True)
        action = self.env['ir.actions.act_window']._for_xml_id('chatter_pin_message.action_pinned_messages')
        pins = self.env['mail.message'].with_user(self.user).search(ast.literal_eval(action['domain']))
        self.assertIn(self.note, pins)
        self.assertNotIn(self.msg, pins)
        self.assertEqual(self.note.action_open_document()['res_id'], self.partner.id)

    def test_settings(self):
        settings = self.env['res.config.settings'].create({'chatter_pin_access': 'read', 'chatter_pin_max': 3})
        settings.execute()
        self.assertEqual(self.icp.get_param('chatter_pin_message.access'), 'read')
        self.assertEqual(self.icp.get_param('chatter_pin_message.max'), '3')


@tagged('post_install', '-at_install')
class TestPinTour(HttpCase, PinCommon):

    def test_tour(self):
        third = self.partner.message_post(body='Prefers e-mail over phone', message_type='comment',
                                          subtype_xmlid='mail.mt_note')
        self.partner.chatter_set_message_pin(self.msg.id, True)
        self.partner.chatter_set_message_pin(third.id, True)
        # two pins in the same second must not freeze the chatter
        self.env.cr.execute("UPDATE mail_message SET pinned_at = '2026-01-01 10:00:00' WHERE id IN %s",
                            [(self.msg.id, third.id)])
        self.start_tour(f'/odoo/res.partner/{self.partner.id}', 'chatter_pin_message_tour', login='admin')
        self.note.invalidate_recordset()
        self.assertFalse(self.note.pinned_at)
