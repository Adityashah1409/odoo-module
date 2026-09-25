from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.my_backend_theme.models.bookmark import is_safe_backend_url
from odoo.addons.my_backend_theme.models.theme_config import normalize_hotkey, sanitize_value


@tagged('post_install', '-at_install')
class TestNavigationFeatures(TransactionCase):
    """Bookmarks, recently viewed records, quick create and global search are
    per-user features: every test checks that a user only ever sees what
    their own access rights allow."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ThemeConfig = cls.env['my.theme.config']
        # Odoo 20 needs "Contact Creation" (group_partner_manager) to create contacts.
        cls.user = new_test_user(cls.env, login='mbt_nav_user', groups='base.group_user,base.group_partner_manager')
        cls.other_user = new_test_user(cls.env, login='mbt_nav_other', groups='base.group_user')
        cls.portal_user = new_test_user(cls.env, login='mbt_nav_portal', groups='base.group_portal')
        cls.partner = cls.env['res.partner'].create({'name': 'Mbt Searchable Partner'})
        cls.Bookmark = cls.env['my.theme.bookmark']
        cls.Recent = cls.env['my.theme.recent']
        cls.QuickCreate = cls.env['my.theme.quick.create']
        cls.SearchModel = cls.env['my.theme.search.model']

    # ------------------------------------------------------------------
    # Bookmarks
    # ------------------------------------------------------------------

    def test_bookmark_url_safety(self):
        for url in ('/odoo', '/odoo/contacts', '/odoo/action-12/5?debug=1'):
            self.assertTrue(is_safe_backend_url(url), url)
        for url in (
            'https://evil.example/odoo', '//evil.example/odoo', 'javascript:alert(1)',
            '/web/login', '/odoofake', '', None, '/odoo/' + 'x' * 2000,
        ):
            self.assertFalse(is_safe_backend_url(url), url)
        with self.assertRaises(ValidationError):
            self.Bookmark.with_user(self.user).create({'name': 'Bad', 'url': 'https://evil.example/odoo'})

    def test_bookmark_toggle_and_privacy(self):
        Bookmark = self.Bookmark.with_user(self.user)
        result = Bookmark.toggle_bookmark('/odoo/contacts/%s' % self.partner.id, 'Partner', 'res.partner', self.partner.id)
        self.assertEqual(result['url'], '/odoo/contacts/%s' % self.partner.id)
        self.assertEqual([b['name'] for b in Bookmark.get_bookmarks()], ['Partner'])
        # Nobody else sees it, even by id.
        other = self.Bookmark.with_user(self.other_user)
        self.assertFalse(other.get_bookmarks())
        self.assertFalse(other.search([('id', '=', result['id'])]))
        with self.assertRaises(AccessError):
            other.browse(result['id']).unlink()
        # Toggling again removes it.
        self.assertFalse(Bookmark.toggle_bookmark('/odoo/contacts/%s' % self.partner.id, 'Partner'))
        self.assertFalse(Bookmark.get_bookmarks())

    def test_bookmark_requires_read_access(self):
        # Internal users cannot read ir.config_parameter records.
        param = self.env['ir.config_parameter'].sudo().search([], limit=1)
        with self.assertRaises(AccessError):
            self.Bookmark.with_user(self.user).toggle_bookmark(
                '/odoo/x/%s' % param.id, 'Param', 'ir.config_parameter', param.id)

    def test_bookmark_rename(self):
        Bookmark = self.Bookmark.with_user(self.user)
        data = Bookmark.toggle_bookmark('/odoo/contacts', 'Contacts')
        renamed = Bookmark.browse(data['id']).rename('  My contacts  ')
        self.assertEqual(renamed['name'], 'My contacts')
        # An empty name keeps the old one.
        self.assertEqual(Bookmark.browse(data['id']).rename('   ')['name'], 'My contacts')

    # ------------------------------------------------------------------
    # Recently viewed
    # ------------------------------------------------------------------

    def test_recent_tracking_and_limit(self):
        self.ThemeConfig._set_global_config({'recent_limit': 5})
        partners = self.env['res.partner'].create([{'name': 'Mbt Recent %s' % i} for i in range(7)])
        Recent = self.Recent.with_user(self.user)
        for partner in partners:
            self.assertTrue(Recent.track('res.partner', partner.id))
        entries = Recent.get_recent()
        self.assertEqual(len(entries), 5)
        # Most recent first, older ones trimmed.
        self.assertEqual(entries[0]['res_id'], partners[-1].id)
        self.assertNotIn(partners[0].id, [e['res_id'] for e in entries])
        # Viewing a record again moves it up instead of duplicating it.
        Recent.track('res.partner', partners[3].id)
        entries = Recent.get_recent()
        self.assertEqual(entries[0]['res_id'], partners[3].id)
        self.assertEqual(len({e['res_id'] for e in entries}), len(entries))
        self.assertFalse(self.Recent.with_user(self.other_user).get_recent())
        Recent.clear_recent()
        self.assertFalse(Recent.get_recent())

    def test_recent_ignores_invalid_and_unreadable(self):
        Recent = self.Recent.with_user(self.user)
        self.assertFalse(Recent.track('no.such.model', 1))
        self.assertFalse(Recent.track('res.partner', 'not-an-id'))
        self.assertFalse(Recent.track('res.partner', 999999999))
        param = self.env['ir.config_parameter'].sudo().search([], limit=1)
        self.assertFalse(Recent.track('ir.config_parameter', param.id))
        self.ThemeConfig._set_global_config({'enable_recent': False})
        self.assertFalse(Recent.track('res.partner', self.partner.id))

    def test_recent_hides_records_no_longer_readable(self):
        Recent = self.Recent.with_user(self.user)
        partner = self.env['res.partner'].create({'name': 'Mbt Soon Deleted'})
        Recent.track('res.partner', partner.id)
        partner.unlink()
        self.assertNotIn(partner.id, [e['res_id'] for e in Recent.get_recent()])

    # ------------------------------------------------------------------
    # Quick create
    # ------------------------------------------------------------------

    def test_quick_create_respects_groups_and_rights(self):
        self.QuickCreate.search([]).unlink()
        self.QuickCreate.create([
            {'name': 'Contact', 'model_id': self.env['ir.model']._get_id('res.partner'), 'icon': 'person_add'},
            {'name': 'Admins only', 'model_id': self.env['ir.model']._get_id('res.partner'),
             'group_ids': [(4, self.env.ref('base.group_system').id)]},
            {'name': 'Parameter', 'model_id': self.env['ir.model']._get_id('ir.config_parameter')},
        ])
        names = [item['name'] for item in self.QuickCreate.with_user(self.user).get_quick_create_items()]
        # No "Admins only" (group) and no "Parameter" (no create right).
        self.assertEqual(names, ['Contact'])
        admin_names = [item['name'] for item in self.QuickCreate.get_quick_create_items()]
        self.assertIn('Admins only', admin_names)
        self.assertFalse(self.QuickCreate.with_user(self.portal_user).get_quick_create_items())

    def test_quick_create_validation(self):
        model_id = self.env['ir.model']._get_id('res.partner')
        with self.assertRaises(ValidationError):
            self.QuickCreate.create({'name': 'Bad icon', 'model_id': model_id, 'icon': 'x" onerror="'})
        with self.assertRaises(ValidationError):
            self.QuickCreate.create({'name': 'Code', 'model_id': model_id, 'context': "__import__('os')"})
        entry = self.QuickCreate.create({
            'name': 'Company', 'model_id': model_id, 'context': "{'default_is_company': True}",
        })
        item = next(i for i in self.QuickCreate.get_quick_create_items() if i['id'] == entry.id)
        self.assertEqual(item['context'], {'default_is_company': True})

    def test_quick_create_is_admin_managed(self):
        with self.assertRaises(AccessError):
            self.QuickCreate.with_user(self.user).create({
                'name': 'Mine', 'model_id': self.env['ir.model']._get_id('res.partner'),
            })

    # ------------------------------------------------------------------
    # Global search
    # ------------------------------------------------------------------

    def test_global_search(self):
        self.SearchModel.search([]).unlink()
        self.SearchModel.create([
            {'model_id': self.env['ir.model']._get_id('res.partner')},
            {'model_id': self.env['ir.model']._get_id('ir.config_parameter')},
        ])
        self.env['ir.config_parameter'].sudo().set_str('mbt.searchable.partner', 'x')
        groups = self.SearchModel.with_user(self.user).global_search('Searchable')
        # Models the user cannot read are skipped silently.
        self.assertEqual([g['model'] for g in groups], ['res.partner'])
        self.assertIn(self.partner.id, [r['id'] for r in groups[0]['records']])
        # Too short, or turned off: nothing.
        self.assertEqual(self.SearchModel.with_user(self.user).global_search('M'), [])
        self.assertEqual(self.SearchModel.with_user(self.portal_user).global_search('Searchable'), [])
        self.ThemeConfig._set_global_config({'enable_global_search': False})
        self.assertEqual(self.SearchModel.with_user(self.user).global_search('Searchable'), [])

    def test_global_search_limit(self):
        self.SearchModel.search([]).unlink()
        self.SearchModel.create({'model_id': self.env['ir.model']._get_id('res.partner')})
        self.env['res.partner'].create([{'name': 'Mbt Many %s' % i} for i in range(6)])
        self.ThemeConfig._set_global_config({'search_limit': 3})
        groups = self.SearchModel.with_user(self.user).global_search('Mbt Many')
        self.assertEqual(len(groups[0]['records']), 3)

    # ------------------------------------------------------------------
    # Shortcuts
    # ------------------------------------------------------------------

    def test_hotkey_normalisation(self):
        self.assertEqual(normalize_hotkey('Ctrl+Alt+K'), 'alt+control+k')
        self.assertEqual(normalize_hotkey(' Shift + ALT + n '), 'alt+shift+n')
        self.assertEqual(sanitize_value('shortcut_search', 'Shift+Alt+S'), 'alt+shift+s')
        self.assertEqual(sanitize_value('shortcut_search', 'none'), False)
        # Without alt/control, or with an unknown key: back to the default.
        self.assertEqual(sanitize_value('shortcut_search', 'shift+s'), 'alt+shift+f')
        self.assertEqual(sanitize_value('shortcut_search', 'alt+f5'), 'alt+shift+f')

    def test_duplicate_shortcuts_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({
                'mbt_shortcut_search': 'alt+shift+k',
                'mbt_shortcut_bookmarks': 'Shift+Alt+K',
            })
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({'mbt_shortcut_search': 'k'})
        settings = self.env['res.config.settings'].create({
            'mbt_shortcut_search': 'Ctrl+Alt+K', 'mbt_shortcut_dark_mode': 'none',
        })
        settings.execute()
        config = self.ThemeConfig._get_global_config()
        self.assertEqual(config['shortcut_search'], 'alt+control+k')
        self.assertIs(config['shortcut_dark_mode'], False)
