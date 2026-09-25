import odoo.tests
from odoo.tests import HttpCase, tagged

from odoo.addons.web.tests.test_js import HootCommon, unit_test_error_checker


@tagged('post_install', '-at_install')
class TestWebClient(HttpCase):

    def test_session_info_contains_the_theme(self):
        self.env['my.theme.config']._set_global_config({'menu_style': 'sidebar', 'primary_color': '#123456'})
        self.authenticate('admin', 'admin')
        info = self.make_jsonrpc_request('/web/session/get_session_info')
        self.assertEqual(info['backend_theme']['menu_style'], 'sidebar')
        self.assertEqual(info['backend_theme']['primary_color'], '#123456')

    def test_web_manifest_uses_the_navbar_color(self):
        self.env['my.theme.config']._set_global_config({'navbar_color': '#0B3558'})
        manifest = self.url_open('/web/manifest.webmanifest').json()
        self.assertEqual(manifest['theme_color'], '#0b3558')
        self.assertEqual(manifest['background_color'], '#0b3558')
        self.env['my.theme.config']._reset_global_config()
        manifest = self.url_open('/web/manifest.webmanifest').json()
        self.assertNotEqual(manifest['theme_color'], '#0b3558')

    def test_dark_scheme_follows_user_preference(self):
        admin = self.env.ref('base.user_admin')
        admin.mbt_theme_mode = 'dark'
        self.authenticate('admin', 'admin')
        response = self.url_open('/odoo')
        self.assertIn('web.assets_web_dark', response.text)
        self.env['my.theme.config']._set_global_config({'enable_dark_mode': False})
        response = self.url_open('/odoo')
        self.assertNotIn('web.assets_web_dark', response.text)


@tagged('post_install', '-at_install')
class TestThemeUnitTests(HootCommon):
    """Runs the module's JS unit tests (static/tests) in a browser."""

    @odoo.tests.no_retry
    def test_js_unit_tests(self):
        suite = self._generate_hash('@my_backend_theme')
        self.browser_js(
            f'/web/tests?headless&loglevel=2&id={suite}',
            "", "", login='admin', timeout=600,
            success_signal="[HOOT] Test suite succeeded",
            error_checker=unit_test_error_checker,
        )
