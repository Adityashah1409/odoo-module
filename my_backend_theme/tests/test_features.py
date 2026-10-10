import base64
import json

from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from odoo.addons.my_backend_theme.models.theme_config import (
    COLOR_PRESETS, CONFIG_SCHEMA, is_acceptable_value,
)


def encode(data):
    return json.dumps(data).encode()


@tagged('post_install', '-at_install')
class TestAccessibility(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='mbt_a11y_user')

    def test_high_contrast_is_a_user_preference(self):
        user = self.user.with_user(self.user)
        user.write({'mbt_high_contrast': True, 'mbt_ui_scale': '140'})
        settings = self.env['res.users.settings']._find_or_create_for_user(self.user)
        self.assertTrue(settings.mbt_high_contrast)
        self.assertEqual(settings.mbt_ui_scale, '140')
        user.action_mbt_reset_preferences()
        self.assertFalse(settings.mbt_high_contrast)

    def test_company_high_contrast_and_large_scale(self):
        self.env['res.config.settings'].create({'mbt_high_contrast': True, 'mbt_ui_scale': '130'}).execute()
        config = self.env['my.theme.config']._get_global_config()
        self.assertIs(config['high_contrast'], True)
        self.assertEqual(config['ui_scale'], '130')


@tagged('post_install', '-at_install')
class TestColorPresets(TransactionCase):

    def test_presets_for_previews(self):
        presets = self.env['my.theme.config'].get_color_presets()
        self.assertEqual(set(presets), set(COLOR_PRESETS))
        self.assertEqual(presets['ocean']['primary_color'], COLOR_PRESETS['ocean']['primary_color'])
        self.assertEqual(presets['ocean']['label'], 'Ocean')
        self.assertNotIn('custom', presets)


@tagged('post_install', '-at_install')
class TestSettingsTransfer(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Config = cls.env['my.theme.config']
        cls.Transfer = cls.env['my.theme.settings.transfer']
        cls.QuickCreate = cls.env['my.theme.quick.create'].with_context(active_test=False)
        cls.SearchModel = cls.env['my.theme.search.model'].with_context(active_test=False)

    def test_acceptable_values(self):
        for key, value in (
            ('primary_color', '#1f6feb'), ('primary_color', False), ('ui_scale', '140'),
            ('menu_style', 'sidebar'), ('sidebar_width', 300), ('high_contrast', True),
            ('shortcut_search', 'alt+shift+k'), ('shortcut_search', False),
        ):
            self.assertTrue(is_acceptable_value(key, value), (key, value))
        for key, value in (
            ('primary_color', 'red'), ('ui_scale', 140), ('ui_scale', '999'), ('menu_style', ['x']),
            ('sidebar_width', 5000), ('sidebar_width', True), ('sidebar_width', '300'),
            ('high_contrast', 'yes'), ('shortcut_search', 'shift+k'), ('unknown_key', 1),
        ):
            self.assertFalse(is_acceptable_value(key, value), (key, value))

    def test_export_contains_settings_and_entries(self):
        self.Config._set_global_config({'primary_color': '#123456', 'menu_style': 'sidebar'})
        data = self.Transfer._export_data()
        self.assertEqual(data['format'], 'my_backend_theme.settings')
        self.assertEqual(set(data['settings']), set(CONFIG_SCHEMA))
        self.assertEqual(data['settings']['primary_color'], '#123456')
        self.assertIn('res.partner', [entry['model'] for entry in data['quick_create']])
        self.assertIn('res.partner', [entry['model'] for entry in data['search_models']])
        # The exported data is JSON as it is.
        json.dumps(data)

    def test_export_action_returns_a_download(self):
        action = self.Transfer.create({}).action_export()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        self.assertIn('download=true', action['url'])

    def test_round_trip(self):
        self.Config._set_global_config({
            'primary_color': '#123456', 'menu_style': 'compact', 'sidebar_width': 300,
            'high_contrast': True, 'shortcut_recent': 'none', 'enable_tabs': True,
        })
        self.QuickCreate.create({
            'name': 'Company', 'model_id': self.env['ir.model']._get_id('res.company'),
            'icon': 'domain', 'context': "{'default_name': 'New'}",
        })
        exported = self.Transfer._export_data()
        quick_create_count = len(self.QuickCreate.search([]))

        self.Config._reset_global_config()
        self.QuickCreate.search([('model', '=', 'res.company')]).unlink()
        result = self.Transfer._import_data(json.loads(json.dumps(exported)))

        self.assertEqual(result['skipped'], [])
        self.assertEqual(result['settings'], len(CONFIG_SCHEMA))
        self.assertEqual(self.Config._get_global_config(), exported['settings'])
        # Only the missing entry is added back.
        self.assertEqual(result['entries'], 1)
        self.assertEqual(len(self.QuickCreate.search([])), quick_create_count)
        company_entry = self.QuickCreate.search([('model', '=', 'res.company')])
        self.assertEqual(company_entry.icon, 'domain')
        self.assertEqual(company_entry.context, "{'default_name': 'New'}")

    def test_invalid_values_are_skipped_and_reported(self):
        self.Config._reset_global_config()
        result = self.Transfer._import_data({
            'format': 'my_backend_theme.settings',
            'version': 1,
            'settings': {
                'primary_color': 'red;} body {display:none',
                'menu_style': 'sidebar',
                'sidebar_width': 9000,
                'not_a_setting': 1,
            },
            'quick_create': [
                {'name': 'Settings', 'model': 'res.config.settings'},
                {'name': 'Bad icon', 'model': 'res.partner', 'icon': '"><script>'},
                {'name': 'Code', 'model': 'res.partner', 'context': "__import__('os')"},
                {'name': 'Missing', 'model': 'no.such.model'},
                'not an entry',
            ],
            'search_models': [{'model': 'no.such.model'}, {'model': 'res.config.settings'}],
        })
        config = self.Config._get_global_config()
        self.assertEqual(config['menu_style'], 'sidebar')
        self.assertFalse(config['primary_color'])
        self.assertEqual(config['sidebar_width'], 240)
        self.assertEqual(result['settings'], 1)
        self.assertEqual(result['entries'], 0)
        self.assertEqual(len(result['skipped']), 9)
        self.assertFalse(self.QuickCreate.search([('name', 'in', ['Settings', 'Bad icon', 'Code', 'Missing'])]))

    def test_rejects_other_files(self):
        for raw in (
            b'not json',
            b'\xff\xfe binary',
            encode(['a list']),
            encode({'format': 'something.else', 'version': 1}),
            encode({'format': 'my_backend_theme.settings', 'version': 99}),
            b' ' * (600 * 1024),
        ):
            with self.subTest(raw=raw[:20]), self.assertRaises(UserError):
                self.Transfer._parse_file(raw)

    def test_import_action(self):
        self.Config._reset_global_config()
        wizard = self.Transfer.create({
            # Base64, as sent by the web client.
            'file': base64.b64encode(encode({
                'format': 'my_backend_theme.settings', 'version': 1,
                'settings': {'list_striped': True, 'ui_scale': 'huge'},
            })).decode(),
            'filename': 'theme.json',
        })
        action = wizard.action_import()
        self.assertEqual(action['res_id'], wizard.id)
        self.assertEqual(wizard.state, 'done')
        self.assertIn('1 settings', wizard.result_message)
        self.assertIn('ui_scale', wizard.result_message)
        self.assertIs(self.Config._get_global_config()['list_striped'], True)
        self.assertEqual(wizard.action_reload()['tag'], 'reload')
        dialog = self.env['res.config.settings'].create({}).action_mbt_import_settings()
        self.assertEqual(dialog['res_model'], 'my.theme.settings.transfer')
        with self.assertRaises(UserError):
            self.Transfer.create({}).action_import()

    def test_only_administrators(self):
        user = new_test_user(self.env, login='mbt_transfer_user', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.Transfer.with_user(user).create({}).action_export()


@tagged('post_install', '-at_install')
class TestWorkspace(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='mbt_ws_user', groups='base.group_user')
        cls.action = cls.env.ref('my_backend_theme.action_my_theme_workspace')
        cls.menu = cls.env.ref('my_backend_theme.menu_my_theme_workspace')

    def test_menu_follows_the_setting(self):
        self.env['res.config.settings'].create({'mbt_enable_workspace': False}).execute()
        self.assertFalse(self.menu.active)
        self.env['res.config.settings'].create({'mbt_enable_workspace': True}).execute()
        self.assertTrue(self.menu.active)
        self.env['my.theme.config']._set_global_config({'enable_workspace': False})
        self.env['my.theme.config']._reset_global_config()
        self.assertTrue(self.menu.active)

    def test_users_choose_it_as_their_home_page(self):
        Users = self.env['res.users'].with_user(self.user)
        self.assertFalse(Users.mbt_is_workspace_home())
        Users.mbt_set_workspace_home(True)
        self.assertEqual(self.user.action_id.id, self.action.id)
        self.assertTrue(Users.mbt_is_workspace_home())
        Users.mbt_set_workspace_home(False)
        self.assertFalse(self.user.action_id)

    def test_portal_users_have_no_home_page(self):
        portal = new_test_user(self.env, login='mbt_ws_portal', groups='base.group_portal')
        with self.assertRaises(AccessError):
            self.env['res.users'].with_user(portal).mbt_set_workspace_home(True)
        self.assertFalse(portal.action_id)

    def test_turning_it_off_keeps_another_home_page(self):
        other_action = self.env.ref('base.action_res_users')
        self.user.action_id = other_action.id
        self.env['res.users'].with_user(self.user).mbt_set_workspace_home(False)
        self.assertEqual(self.user.action_id.id, other_action.id)


@tagged('post_install', '-at_install')
class TestFeatureTours(HttpCase):

    def test_session_info_has_accessibility(self):
        self.env['my.theme.config']._set_global_config({'high_contrast': True})
        self.authenticate('admin', 'admin')
        info = self.make_jsonrpc_request('/web/session/get_session_info')
        self.assertIs(info['backend_theme']['high_contrast'], True)

    def test_export_download(self):
        self.env['my.theme.config']._set_global_config({'navbar_color': '#0b3558'})
        self.authenticate('admin', 'admin')
        action = self.env['my.theme.settings.transfer'].create({}).action_export()
        response = self.url_open(action['url'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['settings']['navbar_color'], '#0b3558')

    def test_workspace_tour(self):
        admin = self.env.ref('base.user_admin')
        partner = self.env['res.partner'].create({'name': 'Mbt Workspace Partner'})
        self.env['my.theme.recent'].with_user(admin).track('res.partner', partner.id)
        self.env['my.theme.bookmark'].with_user(admin).toggle_bookmark('/odoo/contacts', 'Mbt Contacts Bookmark')
        self.start_tour('/odoo/my-workspace', 'my_backend_theme_workspace', login='admin')
        self.assertEqual(admin.action_id.id, self.env.ref('my_backend_theme.action_my_theme_workspace').id)
        settings = self.env['res.users.settings']._find_or_create_for_user(admin)
        self.assertTrue(settings.mbt_high_contrast)

    def test_color_preset_tour(self):
        self.env['my.theme.config']._reset_global_config()
        self.start_tour('/odoo/settings', 'my_backend_theme_color_preset', login='admin')
        config = self.env['my.theme.config']._get_global_config()
        self.assertEqual(config['primary_color'], COLOR_PRESETS['forest']['primary_color'])
        self.assertEqual(config['navbar_color'], COLOR_PRESETS['forest']['navbar_color'])
