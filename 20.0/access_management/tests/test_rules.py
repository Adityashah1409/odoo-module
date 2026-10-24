from datetime import datetime, timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import AccessDenied, AccessError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import AccessCommon


@tagged('post_install', '-at_install')
class TestRules(AccessCommon):

    def test_membership(self):
        Rule = self.env['access.rule']
        rule = self.make_rule(group_ids=[(6, 0, self.team.ids)], model_line_ids=[self.model_line(no_delete=True)])
        self.assertEqual(rule.effective_user_ids, self.alice)
        self.assertTrue(rule.is_effective)
        self.assertTrue(Rule.with_user(self.alice)._get_restrictions())
        self.assertIsNone(Rule.with_user(self.bob)._get_restrictions())
        self.assertEqual(self.alice.access_rule_count, 1)
        rule.exclude_user_ids = self.alice
        self.assertIsNone(Rule.with_user(self.alice)._get_restrictions(), 'excluded')
        rule.exclude_user_ids = False
        other = self.env['res.company'].create({'name': 'Other company'})
        rule.company_ids = other
        self.assertIsNone(Rule.with_user(self.alice)._get_restrictions(), 'other company only')
        rule.company_ids = self.env.company
        self.assertTrue(Rule.with_user(self.alice)._get_restrictions())
        rule.active = False
        self.assertIsNone(Rule.with_user(self.alice)._get_restrictions(), 'archived')
        # superuser and sudo are never restricted
        rule.active = True
        self.assertIsNone(Rule.with_user(self.alice).sudo()._get_restrictions())

    def test_dates_and_schedule(self):
        rule = self.make_rule(date_to=fields.Datetime.now() - timedelta(hours=1), no_debug=True)
        self.assertFalse(rule.is_effective)
        self.assertTrue(rule.is_expired)
        self.assertIn(rule, self.env['access.rule'].search([('is_expired', '=', True)]))
        rule.date_to = False
        self.assertTrue(rule.is_effective)
        with self.assertRaises(ValidationError):
            rule.write({'date_from': '2030-01-02 00:00:00', 'date_to': '2030-01-01 00:00:00'})
        # working hours in Brussels, Monday to Friday
        rule.write({'use_schedule': True, 'sat': False, 'sun': False, 'hour_from': 9.0, 'hour_to': 17.5,
                    'tz': 'Europe/Brussels'})
        self.assertTrue(rule._effective_at(datetime(2026, 10, 21, 8, 30)))     # Wed 10:30 Brussels (UTC+2)
        self.assertFalse(rule._effective_at(datetime(2026, 10, 21, 16, 0)))    # Wed 18:00
        self.assertFalse(rule._effective_at(datetime(2026, 10, 24, 10, 0)))    # Saturday
        self.assertFalse(rule._effective_at(datetime(2026, 10, 21, 6, 30)))    # Wed 08:30
        with freeze_time('2026-10-24 10:00:00'):
            self.env['access.rule']._cron_refresh()
            self.assertFalse(rule.is_effective)
        with freeze_time('2026-10-21 08:30:00'):
            self.env['access.rule']._cron_refresh()
            self.assertTrue(rule.is_effective)
        with self.assertRaises(Exception), mute_logger('odoo.sql_db'):
            with self.cr.savepoint():
                rule.write({'hour_from': 18.0, 'hour_to': 9.0})
                self.env.flush_all()

    def test_model_operations(self):
        self.make_rule(model_line_ids=[self.model_line(no_create=True, no_edit=True, no_delete=True)])
        with self.assertRaises(AccessError):
            self.as_alice().create({'name': 'New'})
        with self.assertRaises(AccessError):
            self.bristol.with_user(self.alice).write({'name': 'Renamed'})
        with self.assertRaises(AccessError):
            self.bath.with_user(self.alice).unlink()
        # reading still works, other users are not affected
        self.assertEqual(self.bristol.with_user(self.alice).name, 'Bristol Ltd')
        self.as_bob().create({'name': 'Bob partner'})
        self.bath.with_user(self.bob).write({'name': 'Bath Company'})

    def test_readonly_shortcut(self):
        rule = self.make_rule(model_line_ids=[self.model_line(readonly=True)])
        info = self.env['access.rule'].with_user(self.alice)._model_restrictions('res.partner')
        self.assertEqual(info['ops'], {'create', 'write', 'unlink'})
        self.assertTrue(info['no_import'] and info['no_archive'] and info['no_duplicate'])
        self.assertIn(self.env._('Read-only'), rule.model_line_ids.summary)

    def test_domain_restriction(self):
        self.make_rule(model_line_ids=[self.model_line(domain="[('city', '=', 'Bristol')]")])
        visible = self.as_alice().search([('id', 'in', (self.bristol | self.bath).ids)])
        self.assertEqual(visible, self.bristol)
        with self.assertRaises(AccessError):
            self.bath.with_user(self.alice).read(['name'])
        with self.assertRaises(AccessError):
            self.bath.with_user(self.alice).write({'name': 'x'})
        self.assertEqual(self.as_bob().search_count([('id', 'in', (self.bristol | self.bath).ids)]), 2)
        with self.assertRaises(ValidationError):
            self.make_rule(name='bad', model_line_ids=[self.model_line(domain="[('no_such_field', '=', 1)]")])

    def test_domain_with_user(self):
        self.bristol.user_id = self.alice
        self.make_rule(model_line_ids=[self.model_line(domain="[('user_id', '=', user.id)]")])
        visible = self.as_alice().search([('id', 'in', (self.bristol | self.bath).ids)])
        self.assertEqual(visible, self.bristol)

    def test_readonly_user(self):
        self.make_rule(readonly_user=True)
        with self.assertRaises(AccessError):
            self.as_alice().create({'name': 'New'})
        with self.assertRaises(AccessError):
            self.bristol.with_user(self.alice).write({'phone': '1'})
        with self.assertRaises(AccessError):
            self.env['res.partner.category'].with_user(self.alice).create({'name': 'Tag'})
        # technical models keep working (e.g. their own settings)
        self.env['res.users.settings'].with_user(self.alice)._find_or_create_for_user(self.alice)
        self.assertEqual(self.bristol.with_user(self.alice).name, 'Bristol Ltd')

    def test_menus(self):
        discuss = self.env.ref('mail.menu_root_discuss')
        Menu = self.env['ir.ui.menu']
        self.assertIn(discuss.id, Menu.with_user(self.alice)._visible_menu_ids())
        rule = self.make_rule(menu_ids=[(6, 0, discuss.ids)])
        self.assertNotIn(discuss.id, Menu.with_user(self.alice)._visible_menu_ids())
        self.assertIn(discuss.id, Menu.with_user(self.bob)._visible_menu_ids())
        menus = Menu.with_user(self.alice).load_menus(False)
        self.assertNotIn(discuss.id, menus)
        self.assertTrue(Menu.with_user(self.alice)._access_blocked_action(discuss.action))
        rule.block_menu_actions = False
        self.assertFalse(Menu.with_user(self.alice)._access_blocked_action(discuss.action))
        # an access manager is never locked out of this application
        root = self.env.ref('access_management.menu_access_root')
        self.alice.group_ids |= self.env.ref('access_management.group_access_manager')
        rule.menu_ids |= root
        self.assertIn(root.id, Menu.with_user(self.alice)._visible_menu_ids())

    def test_login_and_api(self):
        Users = self.env['res.users']
        credential = {'login': 'am_alice', 'password': 'am_alice_pw', 'type': 'password'}
        Users.authenticate(credential, {'interactive': False})
        rule = self.make_rule(block_api=True)
        with self.assertRaises(AccessDenied):
            Users.authenticate(credential, {'interactive': False})
        Users.authenticate(credential, {'interactive': True})
        key = self.env['res.users.apikeys'].with_user(self.alice)._generate('rpc', 'test key', fields.Datetime.now() + timedelta(days=1))
        self.assertFalse(self.env['res.users.apikeys']._check_credentials(scope='rpc', key=key))
        rule.write({'block_api': False, 'block_login': True})
        with self.assertRaises(AccessDenied):
            Users.authenticate(credential, {'interactive': True})
        rule.active = False
        self.assertEqual(self.env['res.users.apikeys']._check_credentials(scope='rpc', key=key), self.alice.id)

    def test_exempt_models(self):
        self.make_rule(readonly_user=True, model_line_ids=[self.model_line(no_create=True)])
        self.assertIsNone(self.env['access.rule'].with_user(self.alice)._restriction_domain('access.rule', 'create'))
        self.assertIsNone(self.env['access.rule'].with_user(self.alice)._restriction_domain('mail.message', 'create'))
