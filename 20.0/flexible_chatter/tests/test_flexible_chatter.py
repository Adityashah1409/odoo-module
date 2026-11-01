from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


class TestFlexibleChatter(TransactionCase):

    def setUp(self):
        super().setUp()
        self.user = new_test_user(self.env, 'flex_user', groups='base.group_user')
        self.icp = self.env['ir.config_parameter'].sudo()

    def test_prefs_and_defaults(self):
        self.assertEqual(self.user._flexible_chatter_prefs(), {'position': 'auto', 'width': 0, 'hidden': False})
        self.icp.set_str('flexible_chatter.position', 'bottom')
        self.icp.set_str('flexible_chatter.width', '35')
        self.assertEqual(self.user._flexible_chatter_prefs(), {'position': 'bottom', 'width': 35, 'hidden': False})
        self.user.chatter_position = 'side'
        self.user.chatter_width = 50
        self.assertEqual(self.user._flexible_chatter_prefs()['position'], 'side', 'the user choice wins')
        self.assertEqual(self.user._flexible_chatter_prefs()['width'], 50)

    def test_save_from_the_chatter(self):
        Users = self.env['res.users'].with_user(self.user)
        prefs = Users.flexible_chatter_save({'position': 'side', 'width': 90, 'hidden': True})
        self.assertEqual(prefs, {'position': 'side', 'width': 65, 'hidden': True}, 'width clamped')
        self.assertEqual(Users.flexible_chatter_save({'width': 5})['width'], 20)
        self.assertEqual(Users.flexible_chatter_save({'width': 0})['width'], 0)
        with self.assertRaises(ValueError):
            Users.flexible_chatter_save({'position': 'top'})
        # preferences form
        self.user.with_user(self.user).write({'chatter_position': 'bottom', 'chatter_hidden': False})
        self.assertEqual(self.user.chatter_position, 'bottom')
        with self.assertRaises(ValidationError):
            self.user.with_user(self.user).write({'chatter_width': 99})

    def test_settings(self):
        settings = self.env['res.config.settings'].create({'flexible_chatter_position': 'side',
                                                           'flexible_chatter_width': 40})
        settings.execute()
        self.assertEqual(self.icp.get_str('flexible_chatter.position'), 'side')
        self.assertEqual(self.icp.get_str('flexible_chatter.width'), '40')


@tagged('post_install', '-at_install')
class TestFlexibleChatterTour(HttpCase):

    def test_session_info(self):
        admin = self.env.ref('base.user_admin')
        admin.write({'chatter_position': 'side', 'chatter_width': 40})
        self.authenticate('admin', 'admin')
        info = self.make_jsonrpc_request('/web/session/get_session_info')
        self.assertEqual(info['flexible_chatter'], {'position': 'side', 'width': 40, 'hidden': False})

    def test_tour(self):
        admin = self.env.ref('base.user_admin')
        admin.write({'chatter_position': False, 'chatter_hidden': False, 'chatter_width': 0})
        partner = self.env['res.partner'].create({'name': 'Layout Ltd'})
        partner.message_post(body='Hello', message_type='comment')
        self.start_tour(f'/odoo/res.partner/{partner.id}', 'flexible_chatter_tour', login='admin')
        self.assertEqual(admin.chatter_position, 'bottom')
        self.assertFalse(admin.chatter_hidden)
