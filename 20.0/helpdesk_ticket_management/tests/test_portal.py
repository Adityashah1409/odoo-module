import re

from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestSupportPortal(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_partner = cls.env['res.partner'].create({'name': 'Portal Co', 'is_company': True})
        cls.portal_user = new_test_user(cls.env, 'sd_portal_web', password='sd_portal_web_pw', groups='base.group_portal',
                                        name='Portal Paula', email='paula@portal.example.com')
        cls.portal_user.partner_id.parent_id = cls.company_partner
        cls.own = cls.env['support.ticket'].create({'name': 'Own portal ticket', 'partner_id': cls.portal_user.partner_id.id,
                                                    'description': '<p>Visible description</p>'})
        cls.foreign = cls.env['support.ticket'].create({'name': 'Foreign ticket', 'partner_id': cls.env['res.partner'].create(
            {'name': 'Somebody else'}).id})

    def test_list_and_detail(self):
        self.authenticate('sd_portal_web', 'sd_portal_web_pw')
        home = self.url_open('/my/home')
        self.assertEqual(home.status_code, 200)
        self.assertIn('Support Tickets', home.text)
        page = self.url_open('/my/tickets')
        self.assertEqual(page.status_code, 200)
        self.assertIn(self.own.number, page.text)
        self.assertNotIn(self.foreign.number, page.text)
        detail = self.url_open(f'/my/tickets/{self.own.id}')
        self.assertIn('Visible description', detail.text)
        self.assertIn('o_portal_chatter', detail.text)
        denied = self.url_open(f'/my/tickets/{self.foreign.id}', allow_redirects=False)
        self.assertEqual(denied.status_code, 303)
        html = self.url_open(f'/my/tickets/{self.own.id}?report_type=html')
        self.assertIn('Own portal ticket', html.text)

    def test_access_token(self):
        self.own._portal_ensure_token()
        page = self.url_open(f'/my/tickets/{self.own.id}?access_token={self.own.access_token}')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Own portal ticket', page.text)

    def test_create_ticket(self):
        self.authenticate('sd_portal_web', 'sd_portal_web_pw')
        form = self.url_open('/my/tickets/new')
        self.assertEqual(form.status_code, 200)
        token = re.search(r'name="csrf_token" value="([^"]+)"', form.text).group(1)
        incident = self.env.ref('helpdesk_ticket_management.type_incident')
        empty = self.url_open('/my/tickets/new', data={'csrf_token': token, 'name': '', 'description': ''})
        self.assertIn('Give your request a subject', empty.text)
        response = self.url_open('/my/tickets/new', data={
            'csrf_token': token, 'name': 'VPN is down', 'description': 'Line 1\nLine 2', 'priority': '2',
            'type_id': str(incident.id)}, files={'attachments': ('vpn.log', b'timeout', 'text/plain')})
        self.assertEqual(response.status_code, 200)
        ticket = self.env['support.ticket'].search([('name', '=', 'VPN is down')])
        self.assertEqual(len(ticket), 1)
        self.assertIn(f'/my/tickets/{ticket.id}', response.url)
        self.assertEqual(ticket.channel, 'portal')
        self.assertEqual(ticket.partner_id, self.portal_user.partner_id)
        self.assertEqual((ticket.priority, ticket.type_id), ('2', incident))
        self.assertIn('Line 1', str(ticket.description))
        self.assertEqual(self.env['ir.attachment'].search([('res_model', '=', 'support.ticket'),
                                                           ('res_id', '=', ticket.id)]).name, 'vpn.log')
        # size limit
        self.env['ir.config_parameter'].sudo().set_int('helpdesk_ticket_management.max_attachment_mb', 1)
        big = self.url_open('/my/tickets/new', data={'csrf_token': token, 'name': 'Big', 'description': 'x'},
                            files={'attachments': ('big.bin', b'0' * (1024 * 1024 + 1), 'application/octet-stream')})
        self.assertIn('larger than 1 MB', big.text)
        # switched off
        self.env['ir.config_parameter'].sudo().set_bool('helpdesk_ticket_management.portal_create', False)
        off = self.url_open('/my/tickets/new', allow_redirects=False)
        self.assertEqual(off.status_code, 303)
        self.env['ir.config_parameter'].sudo().set_bool('helpdesk_ticket_management.portal_create', True)
