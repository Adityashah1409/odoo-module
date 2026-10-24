from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from .common import CLIENT
from .fake_hubspot import GOOD_TOKEN, FakeHubspot


@tagged('post_install', '-at_install')
class TestHubspotTour(HttpCase):

    def test_dashboard_tour(self):
        fake = FakeHubspot()
        fake.add('companies', {'name': 'Tour Industries', 'domain': 'tour.example.com'})
        with patch(f'{CLIENT}.requests.request', side_effect=fake.request):
            account = self.env['hubspot.account'].create({'name': 'Tour portal', 'access_token': GOOD_TOKEN})
            account.action_test_connection()
            account.object_ids.write({'import_enabled': False})
            account.object_ids.filtered(lambda o: o.object_type == 'companies').import_enabled = True
            self.start_tour('/odoo/hubspot', 'hubspot_dashboard_tour', login='admin')
        self.assertTrue(self.env['res.partner'].search([('name', '=', 'Tour Industries')]))
