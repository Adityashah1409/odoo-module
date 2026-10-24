import base64
import hashlib
import hmac
import json
import time
from unittest.mock import patch

from odoo.tests import HttpCase, new_test_user, tagged
from odoo.exceptions import AccessError

from .common import CLIENT, HubspotCommon
from .fake_hubspot import GOOD_TOKEN, FakeHubspot


@tagged('post_install', '-at_install')
class TestQueue(HubspotCommon):

    def test_failure_retry_and_skip(self):
        self.enable('companies', direction='export')
        partner = self.env['res.partner'].create({'name': 'Broken Co', 'vat': 'BE0123456789'})  # Odoo 20: a company has a VAT
        self.fake.fail_next += [('POST', r'^/crm/v3/objects/companies$', 400,
                                 {'status': 'error', 'message': 'Property values were not valid'})] * 3
        self.account.max_attempts = 2
        self.account.action_export_now()
        job = self.jobs(res_id=partner.id, object_type='companies')
        self.assertEqual((job.state, job.attempts), ('pending', 1))
        self.assertIn('not valid', job.error)
        self.account.action_process_queue()
        self.assertEqual((job.state, job.attempts), ('failed', 2))
        self.assertEqual(self.account.failed_count, 1)
        self.fake.fail_next.clear()
        job.action_retry()
        self.assertEqual(job.state, 'done')
        self.assertTrue(self.link('companies', partner))
        # the failing job did not roll back the others
        log = job.log_id
        self.assertEqual(log.created, 1)

    def test_cron(self):
        self.fake.add('companies', {'name': 'Cron Co'})
        self.enable('companies')
        self.env['hubspot.account']._cron_sync()
        self.assertTrue(self.env['res.partner'].search([('name', '=', 'Cron Co')]))
        self.assertEqual(self.obj('companies').link_count, 1)

    def test_newer_job_replaces_pending_one(self):
        company = self.fake.add('companies', {'name': 'Twice Co'})
        self.enable('companies')
        self.account._sync(direction='import', process=False)
        self.fake.change('companies', company, name='Twice Co 2')
        self.obj('companies').last_import = False
        self.account._sync(direction='import', process=False)
        self.assertEqual(self.jobs(hubspot_id=company, state='skipped').error, 'Replaced by a newer job.')
        self.account.action_process_queue()
        self.assertEqual(self.record('companies', company).name, 'Twice Co 2')

    def test_dashboard(self):
        self.fake.add('companies', {'name': 'Dash Co'})
        self.enable('companies')
        self.account.action_import_now()
        data = self.env['hubspot.dashboard'].get_dashboard_data()
        self.assertEqual(data['linked_total'], 1)
        self.assertEqual(data['queue']['done_30'], 1)
        self.assertEqual(data['days'][-1]['import'], 1)
        companies = [o for o in data['objects'] if o['key'] == 'companies'][0]
        self.assertTrue(companies['import'] and companies['last_import'])
        self.assertEqual(data['accounts'][0]['state'], 'connected')

    def test_access(self):
        user = new_test_user(self.env, 'hs_sales', groups='sales_team.group_sale_salesman')
        with self.assertRaises(AccessError):
            self.account.with_user(user).read(['name'])
        partner = self.env['res.partner'].with_user(user).create({'name': 'Visible'})
        self.assertNotIn('hubspot_id', partner.with_user(user).fields_get(), 'hidden from non-managers')


@tagged('post_install', '-at_install')
class TestWebhook(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fake = FakeHubspot()
        cls.startClassPatcher(patch(f'{CLIENT}.requests.request', side_effect=cls.fake.request))
        cls.account = cls.env['hubspot.account'].create({'name': 'Hooks', 'access_token': GOOD_TOKEN,
                                                         'webhook_secret': 'client-secret'})
        cls.account.action_test_connection()
        cls.account.object_ids.write({'import_enabled': False})
        cls.account.object_ids.filtered(lambda o: o.object_type == 'companies').import_enabled = True

    def _post(self, events, secret='client-secret', age=0):
        body = json.dumps(events)
        url = f'{self.base_url()}/hubspot/webhook/{self.account.id}'
        timestamp = str(int((time.time() - age) * 1000))
        signature = base64.b64encode(hmac.new(secret.encode(), f'POST{url}{body}{timestamp}'.encode(),
                                              hashlib.sha256).digest()).decode()
        return self.url_open(url, data=body, headers={'Content-Type': 'application/json',
                                                      'X-HubSpot-Signature-v3': signature,
                                                      'X-HubSpot-Request-Timestamp': timestamp})

    def test_webhook(self):
        company = self.fake.add('companies', {'name': 'Hooked Co'})
        response = self._post([{'subscriptionType': 'company.creation', 'objectId': int(company)},
                               {'subscriptionType': 'company.propertyChange', 'objectId': int(company)},
                               {'subscriptionType': 'object.creation', 'objectTypeId': '0-7', 'objectId': 99},
                               {'subscriptionType': 'ticket.creation', 'objectId': 5}])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['queued'], 1, 'duplicates and disabled objects are ignored')
        job = self.env['hubspot.queue'].search([('account_id', '=', self.account.id), ('hubspot_id', '=', company)])
        self.assertFalse(job.payload)
        self.account.action_process_queue()
        partner = self.env['res.partner'].search([('name', '=', 'Hooked Co')])
        self.assertEqual(job.state, 'done')
        # deletion archives the Odoo record
        self._post([{'subscriptionType': 'company.deletion', 'objectId': int(company)}])
        self.account.action_process_queue()
        self.assertFalse(partner.active)
        self.assertFalse(self.env['hubspot.record'].search([('account_id', '=', self.account.id),
                                                            ('hubspot_id', '=', company)]))

    def test_refused(self):
        self.assertEqual(self._post([], secret='wrong').status_code, 401)
        self.assertEqual(self._post([], age=600).status_code, 401, 'replayed request')
        self.assertEqual(self.url_open('/hubspot/webhook/999999', data='[]').status_code, 404)
