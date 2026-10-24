from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import SupportCommon


@tagged('post_install', '-at_install')
class TestSecurity(SupportCommon):

    def test_ticket_rules(self):
        mine = self._ticket()
        billing = self._ticket(team_id=self.other_team.id, name='Invoice question')
        no_team = self._ticket(team_id=False, name='Lost ticket')
        Ticket = self.env['support.ticket']
        visible = Ticket.with_user(self.agent1).search([('id', 'in', (mine | billing | no_team).ids)])
        self.assertEqual(visible, mine | no_team, 'members see their team and tickets without team')
        with self.assertRaises(AccessError):
            billing.with_user(self.agent1).read(['name'])
        billing.user_id = self.agent1
        self.assertTrue(billing.with_user(self.agent1).read(['name']), 'assigned tickets are visible')
        self.other_team.leader_id = self.leader
        self.assertIn(billing, Ticket.with_user(self.leader).search([]), 'leaders see the teams they lead')
        with self.assertRaises(AccessError):
            mine.with_user(self.agent1).unlink()
        with self.assertRaises(AccessError):
            self.env['support.sla'].with_user(self.agent1).create(
                {'name': 'x', 'team_id': self.team.id, 'stage_id': self.stage_progress.id, 'time': 1})

    def test_portal_rules(self):
        portal = new_test_user(self.env, 'sd_portal', groups='base.group_portal', name='Portal Jane')
        portal.partner_id.parent_id = self.customer_company
        colleague_ticket = self._ticket()
        foreign = self._ticket(partner_id=self.other_customer.id)
        visible = self.env['support.ticket'].with_user(portal).search([])
        self.assertEqual(visible, colleague_ticket, "portal users see their company's tickets only")
        with self.assertRaises(AccessError):
            foreign.with_user(portal).read(['name'])
        with self.assertRaises(AccessError):
            colleague_ticket.with_user(portal).write({'name': 'hacked'})
