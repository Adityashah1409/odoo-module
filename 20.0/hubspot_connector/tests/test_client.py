from datetime import datetime

from odoo.tests import tagged

from ..models.hubspot_client import (HubspotClient, HubspotError, from_hubspot_datetime, to_hubspot_datetime,
                                     verify_signature_v3)
from .common import HubspotCommon
from .fake_hubspot import GOOD_TOKEN


@tagged('post_install', '-at_install')
class TestClientAndSetup(HubspotCommon):

    def test_connection_and_metadata(self):
        self.assertEqual(self.account.state, 'connected')
        self.assertEqual(self.account.portal_id, '4242')
        self.assertEqual(self.account.hubspot_currency, 'EUR')
        self.assertEqual(len(self.account.object_ids), 10)
        owner = self.account.owner_ids.filtered(lambda o: o.hubspot_id == '501')
        self.assertEqual(owner.user_id, self.admin, 'owners are matched to users by e-mail')
        self.assertFalse(self.account.owner_ids.filtered(lambda o: o.hubspot_id == '502').user_id)
        won = self.account.stage_ids.filtered(lambda s: s.hubspot_id == 'closedwon')
        self.assertTrue(won.is_won and won.is_closed)
        self.assertEqual(won.crm_stage_id, self.won_stage)
        lost = self.account.stage_ids.filtered(lambda s: s.hubspot_id == 'closedlost')
        self.assertTrue(lost.is_closed and not lost.is_won)
        # fetching again updates, does not duplicate
        self.account.action_fetch_metadata()
        self.assertEqual(len(self.account.owner_ids), 2)
        self.assertEqual(len(self.account.stage_ids), 4)
        self.assertEqual(self.account._record_url('contacts', '7'),
                         'https://app-eu1.hubspot.com/contacts/4242/record/0-1/7')

    def test_bad_token(self):
        account = self.env['hubspot.account'].create({'name': 'Wrong', 'access_token': 'pat-wrong'})
        action = account.action_test_connection()
        self.assertEqual(account.state, 'error')
        self.assertIn('Authentication credentials', account.last_error)
        self.assertEqual(action['params']['type'], 'danger')

    def test_retry_on_rate_limit_and_errors(self):
        self.fake.fail_next.append(('GET', r'/account-info', 429, {'message': 'Too many requests'}))
        client = HubspotClient(GOOD_TOKEN)
        self.assertEqual(client.account_info()['portalId'], 4242)
        self.assertTrue(self.sleep.called, 'waits before retrying')
        self.fake.fail_next += [('GET', r'/account-info', 500, {'message': 'oops'})] * 4
        with self.assertRaises(HubspotError) as error:
            client.account_info()
        self.assertEqual(error.exception.status, 500)
        self.fake.fail_next.clear()
        with self.assertRaises(HubspotError):
            HubspotClient('')

    def test_pagination(self):
        ids = [self.fake.add('products', {'name': f'Item {index}'}) for index in range(230)]
        client = HubspotClient(GOOD_TOKEN)
        self.assertEqual(len(list(client.iter_objects('products', ['name']))), 230)
        since = from_hubspot_datetime(self.fake.get('products', ids[198])['updatedAt'])
        changed = list(client.iter_objects('products', ['name'], 'hs_lastmodifieddate', since))
        self.assertEqual(len(changed), 32, 'search returns the objects modified since the date')

    def test_helpers(self):
        self.assertEqual(from_hubspot_datetime('2026-03-02T15:04:05.123Z'), datetime(2026, 3, 2, 15, 4, 5, 123000))
        self.assertEqual(from_hubspot_datetime('1772463600000'), datetime(2026, 3, 2, 15, 0))
        self.assertIsNone(from_hubspot_datetime('not a date'))
        self.assertEqual(to_hubspot_datetime(datetime(2026, 3, 2, 15, 0)), '2026-03-02T15:00:00.000Z')
        import base64
        import hashlib
        import hmac
        body = '[{"objectId": 1}]'
        signature = base64.b64encode(hmac.new(b'secret', f'POSThttps://x.test/hook{body}1700000000000'.encode(),
                                              hashlib.sha256).digest()).decode()
        self.assertTrue(verify_signature_v3('secret', 'POST', 'https://x.test/hook', body, '1700000000000', signature,
                                            now=1700000000))
        self.assertFalse(verify_signature_v3('secret', 'POST', 'https://x.test/hook', body, '1700000000000', signature,
                                             now=1700000400), 'older than 5 minutes')
        self.assertFalse(verify_signature_v3('other', 'POST', 'https://x.test/hook', body, '1700000000000', signature,
                                             now=1700000000))
