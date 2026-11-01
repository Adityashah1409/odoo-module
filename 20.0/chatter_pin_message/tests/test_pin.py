import ast

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user


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
        cls.icp.set_str('chatter_pin_message.max', 5)
        cls.icp.set_str('chatter_pin_message.access', 'write')


class TestPin(PinCommon):

    def test_pin_and_unpin(self):
        write_date = self.note.write_date
        self.assertTrue(self.partner.with_user(self.user).set_message_pin(self.note.id, True))
        self.note.invalidate_recordset()
        self.assertTrue(self.note.pinned_at)
        self.assertEqual(self.note.pinned_by_id, self.user)
        self.assertEqual(self.note.write_date, write_date, 'pinning does not change the message')
        # pin twice is harmless and keeps who pinned first
        self.assertFalse(self.partner.set_message_pin(self.note.id, True))
        self.assertEqual(self.note.pinned_by_id, self.user)
        self.partner.with_user(self.user).set_message_pin(self.note.id, False)
        self.note.invalidate_recordset()
        self.assertFalse(self.note.pinned_at)
        self.assertFalse(self.note.pinned_by_id)

    def test_wrong_messages(self):
        with self.assertRaises(UserError):
            self.other.set_message_pin(self.note.id, True)
        with self.assertRaises(UserError):
            self.partner.set_message_pin(self.tracking.id, True)

    def test_limit(self):
        self.icp.set_str('chatter_pin_message.max', 1)
        self.partner.set_message_pin(self.note.id, True)
        with self.assertRaises(UserError):
            self.partner.set_message_pin(self.msg.id, True)
        self.icp.set_str('chatter_pin_message.max', 0)
        self.partner.set_message_pin(self.msg.id, True)
        self.assertEqual(self.env['mail.message'].search_count(self.partner._chatter_pinned_domain()), 2)

    def test_access(self):
        # an employee without the Contact Creation right can read the partner but not edit it
        reader = new_test_user(self.env, 'pin_reader', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.partner.with_user(reader).set_message_pin(self.note.id, True)
        self.icp.set_str('chatter_pin_message.access', 'read')
        self.partner.with_user(reader).set_message_pin(self.note.id, True)
        self.assertTrue(self.note.pinned_at)
        portal = new_test_user(self.env, 'pin_portal', groups='base.group_portal')
        with self.assertRaises(AccessError):
            self.partner.with_user(portal).set_message_pin(self.msg.id, True)

    def test_overview(self):
        self.partner.set_message_pin(self.note.id, True)
        action = self.env['ir.actions.act_window']._for_xml_id('chatter_pin_message.action_pinned_messages')
        pins = self.env['mail.message'].with_user(self.user).search(ast.literal_eval(action['domain']))
        self.assertIn(self.note, pins)
        self.assertNotIn(self.msg, pins)
        self.assertEqual(self.note.action_open_document()['res_id'], self.partner.id)

    def test_settings(self):
        settings = self.env['res.config.settings'].create({'chatter_pin_access': 'read', 'chatter_pin_max': 3})
        settings.execute()
        self.assertEqual(self.icp.get_str('chatter_pin_message.access'), 'read')
        self.assertEqual(self.icp.get_str('chatter_pin_message.max'), '3')


    def test_channel_pins_untouched(self):
        """ Channels keep Odoo's own rules, and who pinned is remembered there too. """
        self.icp.set_int('chatter_pin_message.max', 1)
        channel = self.env['discuss.channel'].create({'name': 'Team', 'channel_type': 'channel'})
        channel._add_members(users=self.user)
        m1 = channel.message_post(body='one', message_type='comment')
        m2 = channel.message_post(body='two', message_type='comment')
        channel.with_user(self.user).set_message_pin(m1.id, True)
        channel.with_user(self.user).set_message_pin(m2.id, True)
        self.assertTrue(m1.pinned_at and m2.pinned_at, 'no limit on channels')
        self.assertEqual(m2.pinned_by_id, self.user)
