import json
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from ..models import powerbi_dataset

MODULE = 'odoo.addons.powerbi_connector.models.powerbi_connection'


class FakeResponse:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.payload = payload
        self.content = json.dumps(payload).encode() if payload is not None else b''
        self.text = self.content.decode()

    def json(self):
        return self.payload


class FakePowerBI:
    """Records API calls; answers like Power BI."""

    def __init__(self):
        self.calls = []
        self.token_calls = 0
        self.fail = False

    def post(self, url, data=None, timeout=None):
        self.token_calls += 1
        return FakeResponse(200, {'access_token': f'token-{self.token_calls}', 'expires_in': 3600})

    def request(self, method, url, json=None, timeout=None, headers=None):
        self.calls.append((method, url.split('/myorg/')[1], json, headers['Authorization']))
        if self.fail:
            return FakeResponse(403, {'error': {'code': 'Unauthorized', 'message': 'Service principal not allowed'}})
        if method == 'POST' and url.endswith('datasets?defaultRetentionPolicy=basicFIFO'):
            return FakeResponse(201, {'id': 'ds-123', 'name': json['name']})
        if method == 'GET':
            return FakeResponse(200, {'value': [{'id': 'ds-1'}]})
        return FakeResponse(200, None)


class PowerBICase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.connection = cls.env['powerbi.connection'].create({
            'name': 'Finance', 'tenant_id': 'tenant', 'client_id': 'client', 'client_secret': 'secret',
            'workspace_id': 'ws-1'})
        Field = cls.env['ir.model.fields']
        cls.belgium = cls.env.ref('base.be')
        cls.partners = cls.env['res.partner'].create([
            {'name': f'PBI customer {i}', 'ref': 'PBI', 'country_id': cls.belgium.id, 'type': 'contact'}
            for i in range(5)])
        cls.dataset = cls.env['powerbi.dataset'].create({
            'name': 'Customers', 'mode': 'push', 'connection_id': cls.connection.id,
            'table_ids': [
                (0, 0, {'name': 'Customers', 'model_id': cls.env['ir.model']._get('res.partner').id,
                        'domain': "[('ref', '=', 'PBI')]",
                        'column_ids': [(0, 0, {'field_id': Field._get('res.partner', f).id})
                                       for f in ('name', 'country_id', 'type', 'active', 'create_date')]}),
                (0, 0, {'name': 'Countries', 'model_id': cls.env['ir.model']._get('res.country').id,
                        'domain': "[('code', 'in', ['BE', 'FR'])]",
                        'column_ids': [(0, 0, {'field_id': Field._get('res.country', f).id}) for f in ('name', 'code')]}),
            ]})
        cls.customers = cls.dataset.table_ids.filtered(lambda t: t.name == 'Customers')

    def setUp(self):
        super().setUp()
        self.api = FakePowerBI()
        for target, attr in (('requests.post', 'post'), ('requests.request', 'request')):
            patcher = patch(f'{MODULE}.{target}', side_effect=getattr(self.api, attr))
            patcher.start()
            self.addCleanup(patcher.stop)


@tagged('post_install', '-at_install')
class TestPowerBI(PowerBICase):

    def test_schema_types_and_relationships(self):
        schema = self.dataset._schema()
        customers = next(t for t in schema['tables'] if t['name'] == 'Customers')
        self.assertEqual(customers['columns'], [
            {'name': 'id', 'dataType': 'Int64'}, {'name': 'name', 'dataType': 'String'},
            {'name': 'country_id', 'dataType': 'Int64'}, {'name': 'type', 'dataType': 'String'},
            {'name': 'active', 'dataType': 'Boolean'}, {'name': 'create_date', 'dataType': 'Datetime'}])
        self.assertEqual(schema['relationships'], [{
            'name': 'Customers_country_id', 'fromTable': 'Customers', 'fromColumn': 'country_id',
            'toTable': 'Countries', 'toColumn': 'id', 'crossFilteringBehavior': 'OneDirection'}])

    def test_rows_conversion(self):
        rows = self.customers._rows(self.partners[:1])
        self.assertEqual(rows[0]['country_id'], self.belgium.id)
        self.assertEqual(rows[0]['type'], 'Contact', "selection label, not key")
        self.assertIs(rows[0]['active'], True)
        self.assertRegex(rows[0]['create_date'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$')

    def test_token_is_cached(self):
        self.connection.action_test_connection()
        self.connection.action_test_connection()
        self.assertEqual(self.api.token_calls, 1)
        self.assertEqual(self.connection.state, 'connected')
        self.connection.sudo().token_expiry = fields.Datetime.now() + timedelta(minutes=2)
        self.connection.action_test_connection()
        self.assertEqual(self.api.token_calls, 2, "renewed shortly before expiry")

    def test_publish_and_full_push(self):
        self.dataset.action_publish()
        self.assertEqual((self.dataset.state, self.dataset.powerbi_dataset_id), ('published', 'ds-123'))
        method, path, payload, auth = self.api.calls[0]
        self.assertEqual((method, path), ('POST', 'groups/ws-1/datasets?defaultRetentionPolicy=basicFIFO'))
        self.assertEqual(payload['defaultMode'], 'Push')
        self.assertEqual(auth, 'Bearer token-1')
        self.api.calls.clear()
        with patch.object(powerbi_dataset, 'PUSH_BATCH', 2):
            self.dataset.action_push()
        customer_calls = [c for c in self.api.calls if '/tables/Customers/' in c[1]]
        self.assertEqual([c[0] for c in customer_calls], ['DELETE', 'POST', 'POST', 'POST'], "full refresh in batches of 2")
        self.assertEqual(sum(len(c[2]['rows']) for c in customer_calls if c[0] == 'POST'), 5)
        self.assertTrue(self.customers.last_sync_date)
        self.assertEqual(self.env['powerbi.log'].search_count(
            [('dataset_id', '=', self.dataset.id), ('operation', '=', 'push_full')]), 2)

    def test_incremental_push(self):
        self.dataset.action_push()
        self.assertEqual(self.customers.last_sync_date, self.env.cr.now(), "sync point = push transaction start")
        # simulate: the existing partners were created long ago, the last push happened 1 second ago
        self.customers.last_sync_date = self.env.cr.now() - timedelta(seconds=1)
        self.env.cr.execute("UPDATE res_partner SET create_date = %s WHERE id IN %s",
                            [self.env.cr.now() - timedelta(days=1), tuple(self.partners.ids)])
        self.env['res.partner'].invalidate_model(['create_date'])
        new = self.env['res.partner'].create({'name': 'PBI new', 'ref': 'PBI'})
        self.api.calls.clear()
        self.dataset.action_push_incremental()
        customer_calls = [c for c in self.api.calls if '/tables/Customers/' in c[1]]
        self.assertEqual([c[0] for c in customer_calls], ['POST'], "no delete in incremental mode")
        self.assertEqual([r['id'] for r in customer_calls[0][2]['rows']], [new.id])

    def test_update_schema(self):
        self.dataset.action_publish()
        self.api.calls.clear()
        self.dataset.action_publish()
        self.assertEqual({(c[0], c[1]) for c in self.api.calls}, {
            ('PUT', 'groups/ws-1/datasets/ds-123/tables/Customers'),
            ('PUT', 'groups/ws-1/datasets/ds-123/tables/Countries')})

    def test_api_error_is_logged(self):
        self.api.fail = True
        self.dataset.action_publish()
        self.assertEqual(self.dataset.state, 'error')
        log = self.env['powerbi.log'].search([('dataset_id', '=', self.dataset.id)], limit=1)
        self.assertEqual(log.status, 'error')
        self.assertIn('Service principal not allowed', log.message)
        action = self.connection.action_test_connection()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertEqual(self.connection.state, 'error')

    def test_scheduled_push(self):
        self.dataset.write({'auto_push': True, 'push_interval': 6})
        self.env['powerbi.dataset']._cron_push()
        self.assertTrue(self.dataset.last_push)
        self.assertAlmostEqual(self.dataset.next_push, fields.Datetime.now() + timedelta(hours=6),
                               delta=timedelta(minutes=1))
        self.api.calls.clear()
        self.env['powerbi.dataset']._cron_push()
        self.assertFalse(self.api.calls, "not due yet")

    def test_validation(self):
        with self.assertRaises(ValidationError):
            self.env['powerbi.dataset'].create({'name': 'x', 'mode': 'push'})
        with self.assertRaises(ValidationError):
            self.customers.name = 'bad name!'

    def test_report_embed_url(self):
        report = self.env['powerbi.report'].create({
            'name': 'Sales', 'tenant_id': 'tenant-1',
            'report_url': 'https://app.powerbi.com/groups/ws-1/reports/rep-9/ReportSection?experience=power-bi'})
        self.assertEqual(report.embed_url,
                         'https://app.powerbi.com/reportEmbed?reportId=rep-9&groupId=ws-1&autoAuth=true&ctid=tenant-1')
        self.assertIn('<iframe', report.embed_html)

    def test_report_visibility(self):
        sales_group = self.env.ref('base.group_partner_manager')
        hidden = self.env['powerbi.report'].create({'name': 'Hidden', 'report_url': 'https://x/reportEmbed?a=1',
                                                     'group_ids': [(6, 0, sales_group.ids)]})
        public = self.env['powerbi.report'].create({'name': 'Public', 'report_url': 'https://x/reportEmbed?a=2'})
        viewer = new_test_user(self.env, 'pbi_viewer', groups='powerbi_connector.group_powerbi_user')
        visible = self.env['powerbi.report'].with_user(viewer).search([])
        self.assertIn(public, visible)
        self.assertNotIn(hidden, visible)


@tagged('post_install', '-at_install')
class TestPowerBIFeed(HttpCase, PowerBICase):

    def test_feed(self):
        self.dataset.mode = 'feed'
        key = self.dataset.access_key
        self.assertEqual(self.url_open(f'/powerbi/feed/{self.dataset.id}/Customers').status_code, 403)
        self.assertEqual(self.url_open(f'/powerbi/feed/{self.dataset.id}/Customers',
                                       headers={'X-API-Key': 'wrong'}).status_code, 403)
        response = self.url_open(f'/powerbi/feed/{self.dataset.id}/Customers', headers={'X-API-Key': key})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(sorted(r['id'] for r in response.json()), sorted(self.partners.ids))
        index = self.url_open(f'/powerbi/feed/{self.dataset.id}?key={key}').json()
        self.assertEqual([t['name'] for t in index['tables']], ['Customers', 'Countries'])
        self.assertEqual(len(index['relationships']), 1)
        self.assertEqual(self.url_open(f'/powerbi/feed/{self.dataset.id}/Nope', headers={'X-API-Key': key}).status_code, 404)

    def test_feed_respects_user_rights(self):
        portal = new_test_user(self.env, 'pbi_portal', groups='base.group_portal')
        self.dataset.write({'mode': 'feed', 'user_id': portal.id, 'table_ids': [(0, 0, {
            'name': 'Crons', 'model_id': self.env['ir.model']._get('ir.cron').id})]})
        headers = {'X-API-Key': self.dataset.access_key}
        self.assertEqual(self.url_open(f'/powerbi/feed/{self.dataset.id}/Countries', headers=headers).status_code, 200)
        response = self.url_open(f'/powerbi/feed/{self.dataset.id}/Crons', headers=headers)
        self.assertEqual(response.status_code, 403, "the feed user cannot read scheduled actions")
