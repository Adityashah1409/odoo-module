import base64
import json
from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from ..models.access_menu_lock import hash_pin, verify_pin
from .common import AccessCommon


@tagged('post_install', '-at_install')
class TestTools(AccessCommon):

    def test_export_log_and_alert(self):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('access_management.export_alert_threshold', '3')
        ICP.set_param('access_management.alert_emails', 'security@example.com')
        Log = self.env['access.export.log']
        partners = (self.bristol | self.bath).with_user(self.bob)
        partners.export_data(['name', 'city'])
        log = Log.search([('user_id', '=', self.bob.id)])
        self.assertEqual((log.model, log.record_count, log.field_names, log.alert), ('res.partner', 2, 'name, city', False))
        partners.export_data(['name', 'city'])   # next batch of the same export
        self.assertEqual(len(Log.search([('user_id', '=', self.bob.id)])), 1)
        self.assertEqual(log.record_count, 4)
        self.assertTrue(log.alert)
        mail = self.env['mail.mail'].search([('email_to', '=', 'security@example.com')])
        self.assertTrue(mail and 'Bob' in mail.subject)
        # retention
        ICP.set_param('access_management.export_log_days', '30')
        with freeze_time(fields.Datetime.now() + timedelta(days=31)):
            Log._cron_cleanup()
        self.assertFalse(log.exists())

    def test_pin_hash(self):
        stored = hash_pin('2468')
        self.assertTrue(stored.startswith('pbkdf2$'))
        self.assertNotIn('2468', stored)
        self.assertTrue(verify_pin('2468', stored))
        self.assertFalse(verify_pin('2469', stored))
        self.assertFalse(verify_pin('2468', 'garbage'))

    def test_menu_lock(self):
        discuss = self.env.ref('mail.menu_root_discuss')
        Lock = self.env['access.menu.lock']
        with self.assertRaises(ValidationError):
            Lock.create({'menu_id': discuss.id})                 # no code
        with self.assertRaises(ValidationError):
            Lock.create({'menu_id': discuss.id, 'code': '12'})   # too short
        lock = Lock.create({'menu_id': discuss.id, 'code': '2468', 'max_attempts': 2, 'lockout_minutes': 10,
                            'alert_emails': 'security@example.com', 'group_ids': [(6, 0, self.team.ids)]})
        lock.invalidate_recordset(['code'])
        self.assertTrue(lock.has_code)
        self.assertFalse(lock.code, 'the code is never read back')
        action = discuss.action
        self.assertEqual(Lock.with_user(self.alice)._lock_for_action(action), lock)
        self.assertFalse(Lock.with_user(self.bob)._lock_for_action(action), 'not in the group')
        ok, message = lock._try_unlock(self.alice, '1111')
        self.assertFalse(ok)
        self.assertIn('1 attempt', message)
        ok, message = lock._try_unlock(self.alice, '0000')
        self.assertFalse(ok)
        self.assertIn('locked', message)
        self.assertTrue(self.env['mail.mail'].search([('subject', 'ilike', 'Locked menu')]))
        ok, _message = lock._try_unlock(self.alice, '2468')
        self.assertFalse(ok, 'even the right code is refused during the lockout')
        with freeze_time(fields.Datetime.now() + timedelta(minutes=11)):
            ok, _message = lock._try_unlock(self.alice, '2468')
            self.assertTrue(ok)
        self.assertEqual(lock.failed_count, 2)
        lock.code = '13579'
        self.assertTrue(verify_pin('13579', lock.sudo().code_hash))

    def test_access_map(self):
        self.make_rule(model_line_ids=[self.model_line(no_create=True)])
        wizard = self.env['access.map'].create({'user_id': self.alice.id})
        wizard.action_compute()
        line = wizard.line_ids.filtered(lambda l: l.model == 'res.partner')
        self.assertEqual(line.perm_create, 'none')
        self.assertIn(line.perm_read, ('full', 'partial'))
        self.assertNotEqual(line.perm_write, 'none')
        self.assertTrue(line.managed)
        self.assertTrue(line.area)
        self.assertFalse(wizard.line_ids.filtered(lambda l: l.model.startswith('ir.')), 'technical models hidden')
        bob_map = self.env['access.map'].create({'user_id': self.bob.id})
        bob_map.action_compute()
        self.assertNotEqual(bob_map.line_ids.filtered(lambda l: l.model == 'res.partner').perm_create, 'none')
        action = wizard.action_download_xlsx()
        self.assertIn('/web/content/access.map/', action['url'])
        self.assertEqual(base64.b64decode(wizard.xlsx_file)[:2], b'PK', 'an xlsx (zip) file')

    def test_transfer(self):
        discuss = self.env.ref('mail.menu_root_discuss')
        rule = self.make_rule(name='Sales: limited', group_ids=[(6, 0, self.team.ids)], no_debug=True,
                              menu_ids=[(6, 0, discuss.ids)],
                              model_line_ids=[self.model_line(no_delete=True, domain="[('city', '=', 'Bristol')]")],
                              field_line_ids=[self.field_line('phone', 'mask', mask_start=3)],
                              element_line_ids=[(0, 0, {'model_id': self.partner_model.id, 'element_type': 'page',
                                                        'name': 'internal_notes'})])
        Transfer = self.env['access.rule.transfer']
        export = Transfer.create({'mode': 'export', 'rule_ids': [(6, 0, rule.ids)]})
        export.action_export()
        data = json.loads(base64.b64decode(export.file))
        self.assertEqual(data['format'], 'access_management')
        item = data['rules'][0]
        self.assertEqual(item['menus'][0]['xmlid'], 'mail.menu_root_discuss')
        self.assertEqual(item['models'][0]['model'], 'res.partner')
        self.assertEqual(item['fields'][0]['field'], 'phone')
        rule.unlink()

        def run(payload, dry_run):
            wizard = Transfer.create({'mode': 'import', 'dry_run': dry_run,
                                      'file': base64.b64encode(json.dumps(payload).encode()).decode()})
            wizard.action_import()
            return wizard.result

        result = run(data, True)
        self.assertIn('Created: 1', result)
        self.assertFalse(self.env['access.rule'].search([('name', '=', 'Sales: limited')]), 'dry run saves nothing')
        result = run(data, False)
        imported = self.env['access.rule'].search([('name', '=', 'Sales: limited')])
        self.assertEqual((imported.menu_ids, imported.group_ids), (discuss, self.team))
        self.assertEqual(imported.field_line_ids.mask_start, 3)
        self.assertEqual(imported.model_line_ids.domain, "[('city', '=', 'Bristol')]")
        self.assertIn('Skipped: 1', run(data, False), 'same content')
        data['rules'][0]['no_debug'] = False
        data['rules'][0]['models'].append({'model': 'no.such.model', 'no_create': True})
        result = run(data, False)
        self.assertIn('Updated: 1', result)
        self.assertIn('no.such.model', result)
        self.assertFalse(imported.no_debug)
        with self.assertRaises(UserError):
            Transfer.create({'mode': 'import', 'file': base64.b64encode(b'{"not": "ours"}').decode()}).action_import()

    def test_dashboard(self):
        self.make_rule(menu_ids=[(6, 0, self.env.ref('mail.menu_root_discuss').ids)],
                       model_line_ids=[self.model_line(no_create=True)])
        self.make_rule(name='Old', date_to=fields.Datetime.now() - timedelta(days=1), no_debug=True)
        self.bath.with_user(self.bob).export_data(['name'])
        data = self.env['access.dashboard'].get_data()
        self.assertEqual(data['kpis']['rules'], 2)
        self.assertEqual(data['kpis']['effective'], 1)
        self.assertEqual(data['kpis']['expired'], 1)
        self.assertEqual(data['kpis']['users'], 1)
        self.assertEqual(data['kpis']['exports'], 1)
        self.assertEqual({k['key']: k['count'] for k in data['kinds']}['menus'], 1)
        self.assertEqual(data['models'][0]['name'], self.partner_model.name)
        self.assertEqual(data['users'][0]['name'], 'Alice')
        self.assertEqual(len(data['days']), 7)
        self.env['access.rule'].action_archive_expired()
        self.assertEqual(self.env['access.dashboard'].get_data()['kpis']['rules'], 1)
