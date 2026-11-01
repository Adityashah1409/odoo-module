from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


class TestChatterOrder(TransactionCase):

    def test_effective_order_and_toggle(self):
        user = new_test_user(self.env, 'order_user', groups='base.group_user')
        icp = self.env['ir.config_parameter'].sudo()
        self.assertEqual(user._chatter_effective_order(), 'desc')
        icp.set_str('chatter_sort_by_date.default_order', 'asc')
        self.assertEqual(user._chatter_effective_order(), 'asc', 'company default')
        self.env['res.users'].with_user(user).chatter_set_message_order('desc')
        self.assertEqual(user.chatter_message_order, 'desc')
        self.assertEqual(user._chatter_effective_order(), 'desc', 'the user choice wins')
        with self.assertRaises(ValueError):
            self.env['res.users'].with_user(user).chatter_set_message_order('random')
        # the user can change it in the preferences
        user.with_user(user).write({'chatter_message_order': 'asc'})
        self.assertEqual(user.chatter_message_order, 'asc')

    def test_settings(self):
        self.env['res.config.settings'].create({'chatter_default_order': 'asc'}).execute()
        self.assertEqual(self.env['ir.config_parameter'].sudo().get_str('chatter_sort_by_date.default_order'),
                         'asc')


@tagged('post_install', '-at_install')
class TestChatterOrderTour(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].with_context(mail_create_nolog=True).create({'name': 'Timeline Ltd'})
        for i in range(1, 36):
            cls.partner.message_post(body=f'Note {i:02d}', message_type='comment', subtype_xmlid='mail.mt_note')
        cls.admin = cls.env.ref('base.user_admin')

    def test_session_info(self):
        self.authenticate('admin', 'admin')
        self.admin.chatter_message_order = 'asc'
        info = self.make_jsonrpc_request('/web/session/get_session_info')
        self.assertEqual(info['chatter_message_order'], 'asc')

    def test_tour_toggle_and_remember(self):
        self.admin.chatter_message_order = False
        self.start_tour(f'/odoo/res.partner/{self.partner.id}', 'chatter_sort_by_date_tour', login='admin')
        self.assertEqual(self.admin.chatter_message_order, 'asc', 'the toggle is remembered')
        self.start_tour(f'/odoo/res.partner/{self.partner.id}', 'chatter_sort_by_date_remembered_tour',
                        login='admin')
        self.assertEqual(self.admin.chatter_message_order, 'desc')
