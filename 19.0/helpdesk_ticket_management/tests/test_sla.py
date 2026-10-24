from datetime import datetime, timedelta

from odoo import fields
from odoo.tests import tagged

from .common import SupportCommon


@tagged('post_install', '-at_install')
class TestSla(SupportCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tag_vip = cls.env['support.tag'].create({'name': 'VIP'})
        SLA = cls.env['support.sla']
        cls.sla_answer = SLA.create({'name': 'Answer in 4h', 'team_id': cls.team.id, 'stage_id': cls.stage_progress.id,
                                     'time': 4})
        cls.sla_urgent = SLA.create({'name': 'Urgent solved in 8h', 'team_id': cls.team.id, 'priority': '3',
                                     'stage_id': cls.stage_solved.id, 'time': 8})
        cls.sla_vip = SLA.create({'name': 'VIP incidents', 'team_id': cls.team.id, 'stage_id': cls.stage_solved.id,
                                  'time': 16, 'tag_ids': [(6, 0, cls.tag_vip.ids)],
                                  'type_ids': [(6, 0, cls.type_incident.ids)]})
        cls.sla_acme = SLA.create({'name': 'Acme contract', 'team_id': cls.team.id, 'stage_id': cls.stage_waiting.id,
                                   'time': 2, 'partner_ids': [(6, 0, cls.customer_company.ids)]})

    def test_deadline_working_hours(self):
        monday_15 = datetime(2026, 3, 2, 15, 0)
        self.assertEqual(self.sla_answer._deadline(monday_15), datetime(2026, 3, 3, 11, 0),
                         '2h on Monday + 2h on Tuesday')
        friday_16 = datetime(2026, 3, 6, 16, 0)
        self.assertEqual(self.sla_answer._deadline(friday_16), datetime(2026, 3, 9, 12, 0), 'skips the weekend')
        self.team.resource_calendar_id = False
        self.assertEqual(self.sla_answer._deadline(friday_16), datetime(2026, 3, 6, 20, 0), '24/7 without calendar')

    def test_policies_match(self):
        ticket = self._ticket(partner_id=self.other_customer.id)
        self.assertEqual(ticket.sla_status_ids.sla_id, self.sla_answer)
        ticket.priority = '3'
        self.assertEqual(ticket.sla_status_ids.sla_id, self.sla_answer | self.sla_urgent)
        ticket.write({'tag_ids': [(4, self.tag_vip.id)], 'type_id': self.type_incident.id})
        self.assertIn(self.sla_vip, ticket.sla_status_ids.sla_id)
        ticket.priority = '1'
        self.assertNotIn(self.sla_urgent, ticket.sla_status_ids.sla_id, 'removed when it no longer applies')
        ticket.partner_id = self.customer
        self.assertIn(self.sla_acme, ticket.sla_status_ids.sla_id, 'customer contract (company of the contact)')
        self.assertEqual(ticket.sla_deadline, min(ticket.sla_status_ids.mapped('deadline')))
        other_team = self._ticket(team_id=self.other_team.id)
        self.assertFalse(other_team.sla_status_ids)
        self.team.use_sla = False
        self.assertFalse(self._ticket().sla_status_ids)

    def test_reach_and_fail(self):
        ticket = self._ticket(partner_id=self.other_customer.id, priority='3')
        answer = ticket.sla_status_ids.filtered(lambda s: s.sla_id == self.sla_answer)
        urgent = ticket.sla_status_ids.filtered(lambda s: s.sla_id == self.sla_urgent)
        ticket.stage_id = self.stage_waiting
        self.assertEqual(answer.status, 'reached', 'a later stage reaches the target')
        self.assertTrue(answer.reached_datetime)
        self.assertEqual(urgent.status, 'ongoing')
        self.assertEqual(ticket.sla_deadline, urgent.deadline)
        urgent.deadline = fields.Datetime.now() - timedelta(hours=1)
        self.env['support.ticket.sla']._cron_check_deadlines()
        self.assertEqual(urgent.status, 'failed')
        self.assertTrue(ticket.sla_fail)
        self.assertEqual(self.team.sla_failed_ticket_count, 1)
        ticket.action_close()
        self.assertEqual(urgent.status, 'failed', 'reached late stays failed')
        self.assertGreater(urgent.exceeded_hours, 0.9)
        self.assertFalse(ticket.sla_deadline)
        self.assertEqual(self.sla_urgent.failed_rate, 100.0)

    def test_closing_reaches_everything(self):
        ticket = self._ticket(partner_id=self.other_customer.id, priority='3')
        ticket.stage_id = self.stage_cancelled
        self.assertEqual(set(ticket.sla_status_ids.mapped('status')), {'reached'})
