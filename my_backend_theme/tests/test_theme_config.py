from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.my_backend_theme.models.theme_config import COLOR_PRESETS, CONFIG_SCHEMA


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
        config = self.ThemeConfig._get_global_config()
        self.assertEqual(set(config), set(CONFIG_SCHEMA))
        for key, (_kind, default, _extra) in CONFIG_SCHEMA.items():
            self.assertEqual(config[key], default, key)

    def test_settings_are_stored_and_normalised(self):
        self.env['res.config.settings'].create({
            'mbt_primary_color': '#1F6FEB',
            'mbt_navbar_color': '#0f172a',
            'mbt_ui_scale': '110',
            'mbt_font_family': 'inter',
            'mbt_reduce_motion': True,
            'mbt_menu_style': 'sidebar',
            'mbt_sidebar_width': 280,
            'mbt_enable_dark_mode': False,
        }).execute()
        config = self.ThemeConfig._get_global_config()
        self.assertEqual(config['primary_color'], '#1f6feb')
        self.assertEqual(config['navbar_color'], '#0f172a')
        self.assertEqual(config['ui_scale'], '110')
        self.assertEqual(config['font_family'], 'inter')
        self.assertIs(config['reduce_motion'], True)
        self.assertEqual(config['menu_style'], 'sidebar')
        self.assertEqual(config['sidebar_width'], 280)
        self.assertIs(config['enable_dark_mode'], False)

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
        self.ICP.set_str('my_backend_theme.sidebar_width', '5000')
        self.ICP.set_str('my_backend_theme.menu_style', '"><script>')
        config = self.ThemeConfig._get_global_config()
        self.assertFalse(config['primary_color'])
        self.assertEqual(config['ui_scale'], '100')
        self.assertEqual(config['font_family'], 'system')
        self.assertEqual(config['sidebar_width'], 240)
        self.assertEqual(config['menu_style'], 'horizontal')

    def test_invalid_sidebar_width_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({'mbt_sidebar_width': 20})

    def test_color_preset_fills_colors(self):
        settings = self.env['res.config.settings'].new({'mbt_color_preset': 'forest'})
        settings._onchange_mbt_color_preset()
        self.assertEqual(settings.mbt_primary_color, COLOR_PRESETS['forest']['primary_color'])
        settings.mbt_color_preset = 'default'
        settings._onchange_mbt_color_preset()
        self.assertFalse(settings.mbt_primary_color)

    def test_theme_mode(self):
        self.ThemeConfig._reset_global_config()
        self.assertEqual(self.user._mbt_get_theme_mode(), 'light')
        self.user.with_user(self.user).mbt_theme_mode = 'dark'
        self.assertEqual(self.user._mbt_get_theme_mode(), 'dark')
        # Disabling dark mode globally wins over the user's choice.
        self.ThemeConfig._set_global_config({'enable_dark_mode': False})
        self.assertEqual(self.user._mbt_get_theme_mode(), 'light')
        self.ThemeConfig._set_global_config({'enable_dark_mode': True, 'default_theme_mode': 'system'})
        self.user.with_user(self.user).mbt_theme_mode = False
        self.assertEqual(self.user._mbt_get_theme_mode(), 'system')

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
