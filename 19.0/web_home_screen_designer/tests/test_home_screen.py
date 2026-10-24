import base64
import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, new_test_user, tagged

PNG = base64.b64encode(base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
)).decode()


@tagged('post_install', '-at_install')
class TestHomeScreen(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Layout = cls.env['home.screen.layout']
        cls.Layout.search([]).unlink()
        cls.env.company.home_screen_allow_user_layout = True
        cls.user = new_test_user(cls.env, login='hs_user', groups='base.group_user', name='Julia Roberts')
        cls.other = new_test_user(cls.env, login='hs_other', groups='base.group_user')
        cls.action = cls.env.ref('web_home_screen_designer.action_home_screen')
        cls.env.ref('base.user_admin').name = 'Mitchell Admin'

    def as_user(self, user=None):
        return self.Layout.with_user(user or self.user)

    def test_defaults(self):
        data = self.as_user().get_home_screen()
        self.assertEqual(data['scope'], 'default')
        self.assertEqual(data['layout']['icon_size'], 64)
        self.assertEqual(data['layout']['background_type'], 'gradient')
        self.assertEqual(data['layout']['hidden_apps'], [])
        self.assertEqual(data['first_name'], 'Julia')
        self.assertFalse(data['is_admin'])
        self.assertEqual(len(data['gradients']), 8)

    def test_company_then_personal_then_reset(self):
        self.Layout.save_home_screen({'gradient': 'ocean', 'columns': 6}, scope='company')
        data = self.as_user().get_home_screen()
        self.assertEqual((data['scope'], data['layout']['gradient'], data['layout']['columns']), ('company', 'ocean', 6))
        data = self.as_user().save_home_screen({'gradient': 'mint', 'hidden_apps': ['base.menu_management']})
        self.assertEqual((data['scope'], data['layout']['gradient']), ('user', 'mint'))
        self.assertEqual(data['layout']['hidden_apps'], ['base.menu_management'])
        # other users still see the company layout
        self.assertEqual(self.as_user(self.other).get_home_screen()['layout']['gradient'], 'ocean')
        data = self.as_user().reset_home_screen()
        self.assertEqual((data['scope'], data['layout']['gradient']), ('company', 'ocean'))

    def test_clean_values(self):
        data = self.as_user().save_home_screen({
            'icon_size': 500, 'columns': 2, 'gap': -5, 'show_names': 0, 'unknown': 'x', 'app_order': ['a', 'b'],
        })
        layout = data['layout']
        self.assertEqual((layout['icon_size'], layout['columns'], layout['gap']), (128, 3, 0))
        self.assertFalse(layout['show_names'])
        self.assertEqual(layout['app_order'], ['a', 'b'])
        self.assertNotIn('unknown', layout)
        with self.assertRaises(UserError):
            self.as_user().save_home_screen({'gradient': 'rainbow'})
        with self.assertRaises(UserError):
            self.as_user().save_home_screen({'hidden_apps': 'base.menu_management'})
        with self.assertRaises(UserError):
            self.as_user().save_home_screen({'icon_size': 'big'})

    def test_rights(self):
        with self.assertRaises(AccessError):
            self.as_user().save_home_screen({'gradient': 'dusk'}, scope='company')
        self.as_user().save_home_screen({'gradient': 'dusk'})
        self.as_user(self.other).save_home_screen({'gradient': 'peach'})
        # record rule: a user reads their own layout and the company one, not another user's
        mine = self.Layout.with_user(self.user).search([])
        self.assertEqual(mine.user_id, self.user)
        # company switch: personal layouts are refused, the company layout is shown
        self.Layout.save_home_screen({'gradient': 'slate'}, scope='company', allow_user_layout=False)
        self.assertFalse(self.env.company.home_screen_allow_user_layout)
        data = self.as_user().get_home_screen()
        self.assertEqual((data['scope'], data['layout']['gradient']), ('company', 'slate'))
        with self.assertRaises(UserError):
            self.as_user().save_home_screen({'gradient': 'mint'})

    def test_open_on_login_and_image(self):
        data = self.as_user().save_home_screen({'background_type': 'image', 'background_image': PNG}, open_on_login=True)
        self.assertEqual(self.user.action_id.id, self.action.id)
        self.assertTrue(data['open_on_login'])
        self.assertTrue(data['layout']['background_url'].startswith('/web/image/home.screen.layout/'))
        self.as_user().save_home_screen({}, open_on_login=False)
        self.assertFalse(self.user.action_id)

    def test_home_screen_tour(self):
        self.start_tour('/odoo/home-screen', 'web_home_screen_designer_tour', login='admin')
        layout = self.Layout.search([('user_id', '=', self.env.ref('base.user_admin').id)])
        self.assertEqual(layout.gradient, 'sunset')
        self.assertEqual(layout.columns, 4)
        self.assertEqual(json.loads(layout.hidden_apps), ['base.menu_management'])
        self.assertEqual(json.loads(layout.app_order)[0], 'base.menu_administration')
