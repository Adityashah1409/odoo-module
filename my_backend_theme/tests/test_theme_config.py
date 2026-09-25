from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestThemeConfig(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.ThemeConfig = cls.env['my.theme.config']
        cls.user = new_test_user(cls.env, login='mbt_user')
        cls.other_user = new_test_user(cls.env, login='mbt_other_user')

    def test_defaults(self):
        self.ThemeConfig._reset_global_config()
        self.assertEqual(self.ThemeConfig._get_global_config(), {
            'primary_color': False,
            'navbar_color': False,
            'ui_scale': 100,
            'font_family': 'system',
            'reduce_motion': False,
        })

    def test_settings_are_stored_and_normalised(self):
        self.env['res.config.settings'].create({
            'mbt_primary_color': '#1F6FEB',
            'mbt_navbar_color': '#0f172a',
            'mbt_ui_scale': '110',
            'mbt_font_family': 'inter',
            'mbt_reduce_motion': True,
        }).execute()
        self.assertEqual(self.ThemeConfig._get_global_config(), {
            'primary_color': '#1f6feb',
            'navbar_color': '#0f172a',
            'ui_scale': 110,
            'font_family': 'inter',
            'reduce_motion': True,
        })

    def test_invalid_color_is_rejected(self):
        for value in ('red', '#fff', '#12345g', '#123456; background: url(x)'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.env['res.config.settings'].create({'mbt_primary_color': value})

    def test_tampered_parameters_fall_back_to_defaults(self):
        # Parameters edited by hand (bypassing the settings form) must never
        # reach the web client unvalidated.
        self.ICP.set_str('my_backend_theme.primary_color', 'red;} body {display:none')
        self.ICP.set_str('my_backend_theme.ui_scale', '999')
        self.ICP.set_str('my_backend_theme.font_family', 'Comic Sans')
        config = self.ThemeConfig._get_global_config()
        self.assertFalse(config['primary_color'])
        self.assertEqual(config['ui_scale'], 100)
        self.assertEqual(config['font_family'], 'system')

    def test_reset_global_config(self):
        self.ICP.set_str('my_backend_theme.primary_color', '#1f6feb')
        self.ICP.set_str('web.base.url', 'http://example.com')
        self.env['res.config.settings'].create({}).action_mbt_reset_defaults()
        self.assertFalse(self.ThemeConfig._get_global_config()['primary_color'])
        self.assertEqual(self.ICP.get_str('web.base.url'), 'http://example.com')

    def test_user_can_edit_own_preferences(self):
        user = self.user.with_user(self.user)
        user.write({'mbt_ui_scale': '120', 'mbt_reduce_motion': True})
        settings = self.env['res.users.settings']._find_or_create_for_user(self.user)
        self.assertEqual(settings.mbt_ui_scale, '120')
        self.assertTrue(settings.mbt_reduce_motion)
        self.assertEqual(user.mbt_ui_scale, '120')

        user.action_mbt_reset_preferences()
        self.assertFalse(settings.mbt_ui_scale)
        self.assertFalse(settings.mbt_reduce_motion)

    def test_user_cannot_read_other_users_preferences(self):
        other_settings = self.env['res.users.settings']._find_or_create_for_user(self.other_user)
        visible = self.env['res.users.settings'].with_user(self.user).search([])
        self.assertNotIn(other_settings, visible)
