from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import SupportCommon


@tagged('post_install', '-at_install')
class TestTicket(SupportCommon):

    def test_defaults(self):
        ticket = self.env['support.ticket'].create({'name': 'No team given'})
        self.assertTrue(ticket.number.startswith('TCK'))
        self.assertEqual(ticket.team_id, self.env.ref('helpdesk_ticket_management.team_support'))
        self.assertEqual(ticket.stage_id, self.stage_new)
        self.assertEqual(ticket.company_id, self.env.company)
        self.assertEqual(ticket.display_name, f'[{ticket.number}] No team given')
        second = self._ticket()
        self.assertNotEqual(second.number, ticket.number)
        self.assertEqual(self.env['support.ticket'].name_search(second.number)[0][0], second.id)
        self.assertIn(self.customer, second.message_partner_ids, "the customer follows the ticket")

    def test_single_default_team(self):
        with self.assertRaises(ValidationError):
            self.team.is_default = True

    def test_assignment_methods(self):
        self.team.assignment_method = 'round_robin'
        tickets = self.env['support.ticket'].create([{'name': f'RR {i}', 'team_id': self.team.id} for i in range(4)])
        self.assertEqual(tickets.mapped('user_id'), self.agent1 | self.agent2)
        self.assertEqual([t.user_id for t in tickets], [self.agent1, self.agent2, self.agent1, self.agent2])
        self.assertTrue(all(tickets.mapped('date_assigned')))
        self.team.assignment_method = 'balanced'
        self._ticket(user_id=self.agent1.id)
        balanced = self._ticket()
        self.assertEqual(balanced.user_id, self.agent2, 'agent2 has fewer open tickets')
        self.team.assignment_method = 'manual'
        self.assertFalse(self._ticket().user_id)

    def test_close_fields_and_reopen(self):
        ticket = self._ticket()
        ticket.with_user(self.agent1).action_close()
        self.assertEqual(ticket.stage_id, self.stage_solved)
        self.assertTrue(ticket.is_closed)
        self.assertEqual(ticket.closed_by_id, self.agent1)
        self.assertTrue(ticket.date_closed)
        ticket.stage_id = self.stage_progress
        self.assertFalse(ticket.is_closed)
        self.assertFalse(ticket.date_closed)

    def test_team_stages(self):
        own_stage = self.env['support.stage'].create({'name': 'Billing check', 'sequence': 1,
                                                      'team_ids': [(6, 0, self.other_team.ids)]})
        self.assertIn(own_stage, self.other_team.stage_ids)
        self.assertNotIn(own_stage, self.team.stage_ids)
        ticket = self._ticket(team_id=self.other_team.id)
        self.assertEqual(ticket.stage_id, own_stage, 'first stage of the team')
        ticket.team_id = self.team
        self.assertEqual(ticket.stage_id, self.stage_new, 'stage of the old team is replaced')

    def test_checklist(self):
        template = self.env['support.checklist.template'].create({
            'name': 'Incident', 'type_ids': [(6, 0, self.type_incident.ids)],
            'line_ids': [(0, 0, {'name': 'Reproduce'}), (0, 0, {'name': 'Fix'}), (0, 0, {'name': 'Confirm with customer'})]})
        ticket = self._ticket(type_id=self.type_incident.id)
        self.assertEqual(ticket.checklist_ids.mapped('name'), ['Reproduce', 'Fix', 'Confirm with customer'])
        ticket.checklist_ids[0].with_user(self.agent1).done = True
        self.assertAlmostEqual(ticket.checklist_progress, 100 / 3, places=2)
        self.assertEqual(ticket.checklist_ids[0].done_by_id, self.agent1)
        other = self.env['support.checklist.template'].create({
            'name': 'Extra', 'line_ids': [(0, 0, {'name': 'Fix'}), (0, 0, {'name': 'Write the KB article'})]})
        ticket.checklist_template_id = other
        self.assertEqual(len(ticket.checklist_ids), 4, 'duplicates are skipped')
        question = self._ticket(type_id=self.type_question.id)
        self.assertFalse(question.checklist_ids)
        question.type_id = self.type_incident
        self.assertEqual(len(question.checklist_ids), 3)
        self.assertTrue(template)

    def test_timers(self):
        ticket = self._ticket()
        other = self._ticket(name='Second')
        ticket.with_user(self.agent1).action_timer_start()
        ticket.with_user(self.agent2).action_timer_start()
        self.assertEqual(ticket.with_user(self.agent1).timer_user_ids, self.agent1 | self.agent2)
        self.assertTrue(ticket.with_user(self.agent1).timer_running)
        with self.assertRaises(UserError):
            other.with_user(self.agent1).action_timer_start()
        self.env['ir.config_parameter'].sudo().set_bool('helpdesk_ticket_management.multi_timer', True)
        other.with_user(self.agent1).action_timer_start()
        entry = ticket.time_entry_ids.filtered(lambda e: e.user_id == self.agent1)
        entry.start = fields.Datetime.now() - timedelta(minutes=45)
        ticket.with_user(self.agent1).action_timer_stop()
        self.assertAlmostEqual(entry.hours, 0.75, places=2)
        self.assertFalse(entry.running)
        self.assertTrue(ticket.time_entry_ids.filtered(lambda e: e.user_id == self.agent2).running)
        ticket.action_close()
        self.assertFalse(ticket.time_entry_ids.filtered('running'), 'closing stops every timer')
        self.assertGreaterEqual(ticket.spent_hours, 0.75)
        with self.assertRaises(UserError):
            ticket.with_user(self.agent1).action_timer_start()

    def test_partner_ticket_count(self):
        self._ticket()
        self._ticket(partner_id=self.customer_company.id)
        self.assertEqual(self.customer.support_ticket_count, 1)
        self.assertEqual(self.customer_company.support_ticket_count, 2, 'company counts its contacts')
        action = self.customer_company.action_view_support_tickets()
        self.assertEqual(self.env['support.ticket'].search_count(action['domain']), 2)

    def test_dashboard_data(self):
        self._ticket(user_id=self.agent1.id, priority='3')
        self._ticket()
        self._ticket(team_id=self.other_team.id)
        done = self._ticket(user_id=self.agent1.id)
        done.with_user(self.agent1).action_close()
        Ticket = self.env['support.ticket']
        data = Ticket.with_user(self.agent1).get_dashboard_data(scope='mine')
        self.assertEqual(data['counts']['open'], 1)
        self.assertEqual(data['counts']['urgent'], 1)
        self.assertEqual(data['counts']['closed_today'], 1)
        self.assertFalse(data['can_all'])
        teams = Ticket.with_user(self.agent1).get_dashboard_data(scope='teams')
        self.assertEqual(teams['counts']['open'], 2)
        self.assertEqual(teams['counts']['unassigned'], 1)
        self.assertEqual(sum(r['count'] for r in teams['by_stage']), 2)
        everything = Ticket.get_dashboard_data(scope='all', team_id=self.other_team.id)
        self.assertEqual(everything['counts']['open'], 1)
        self.assertEqual(len(everything['daily']), 14)
        self.assertEqual(everything['daily'][-1]['count'], 1)
        for key, domain in teams['domains'].items():
            self.assertEqual(Ticket.with_user(self.agent1).search_count(domain), teams['counts'][key], key)

    def test_whatsapp(self):
        ticket = self._ticket()
        wizard = self.env['support.whatsapp.wizard'].create({'ticket_id': ticket.id})
        self.assertIn(ticket.number, wizard.message)
        self.assertIn('/my/tickets/', wizard.message)
        action = wizard.action_send()
        self.assertTrue(action['url'].startswith('https://wa.me/32470123456?text='))
        self.assertIn('Sent by WhatsApp', ticket.message_ids[0].body)
        no_phone = self._ticket(partner_id=self.other_customer.id)
        with self.assertRaises(UserError):
            no_phone.action_open_whatsapp()
