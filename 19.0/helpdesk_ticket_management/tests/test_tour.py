from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestSupportTour(HttpCase):

    def test_dashboard_tour(self):
        self.env['support.ticket'].search([]).write({'active': False})
        self.env['support.ticket'].create({
            'name': 'Tour urgent ticket', 'priority': '3',
            'partner_id': self.env['res.partner'].create({'name': 'Tour Customer'}).id,
        })
        self.start_tour('/odoo/helpdesk-dashboard', 'support_dashboard_tour', login='admin')
        ticket = self.env['support.ticket'].search([('name', '=', 'Tour urgent ticket')])
        self.assertEqual(ticket.user_id, self.env.ref('base.user_admin'))
        self.assertTrue(ticket.time_entry_ids)

    def test_portal_tour(self):
        self.env['ir.config_parameter'].sudo().set_param('helpdesk_ticket_management.portal_create', 'True')
        self.env['res.users'].create({'name': 'Tour Portal', 'login': 'tour_portal', 'password': 'tour_portal',
                                      'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        self.start_tour('/my/tickets', 'support_portal_tour', login='tour_portal')
        ticket = self.env['support.ticket'].search([('name', '=', 'Tour portal request')])
        self.assertEqual(ticket.channel, 'portal')
