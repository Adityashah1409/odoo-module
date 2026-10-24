from unittest.mock import patch

from odoo.tests.common import TransactionCase

from .fake_hubspot import GOOD_TOKEN, FakeHubspot

CLIENT = 'odoo.addons.hubspot_connector.models.hubspot_client'


class HubspotCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_notify_force_send=False))
        cls.fake = FakeHubspot()
        cls.startClassPatcher(patch(f'{CLIENT}.requests.request', side_effect=cls.fake.request))
        cls.sleep = cls.startClassPatcher(patch(f'{CLIENT}._sleep'))
        cls.admin = cls.env.ref('base.user_admin')
        cls.admin.email = 'admin@yourcompany.example.com'
        cls.account = cls.env['hubspot.account'].create({'name': 'Test portal', 'access_token': GOOD_TOKEN})
        cls.account.action_test_connection()
        cls.won_stage = cls.env['crm.stage'].search([('is_won', '=', True)], limit=1)
        cls.first_stage = cls.env['crm.stage'].search([('is_won', '=', False)], limit=1)

    def setUp(self):
        super().setUp()
        self.fake.objects.clear()
        self.fake.associations.clear()
        self.fake.calls.clear()
        self.fake.fail_next.clear()

    def obj(self, object_type):
        return self.account.object_ids.filtered(lambda o: o.object_type == object_type)

    def enable(self, *object_types, direction='import'):
        self.account.object_ids.write({'import_enabled': False, 'export_enabled': False})
        self.account.object_ids.filtered(lambda o: o.object_type in object_types).write({f'{direction}_enabled': True})

    def link(self, object_type, record):
        return self.env['hubspot.record']._get(self.account, object_type, record=record)

    def record(self, object_type, hubspot_id):
        link = self.env['hubspot.record']._get(self.account, object_type, hubspot_id=hubspot_id)
        return link._record() if link else None

    def jobs(self, **filters):
        domain = [('account_id', '=', self.account.id)] + [(k, '=', v) for k, v in filters.items()]
        return self.env['hubspot.queue'].search(domain)
