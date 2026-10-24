from odoo.tests import new_test_user
from odoo.tests.common import TransactionCase


class SupportCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, mail_create_nolog=True, mail_notrack=False))
        ref = cls.env.ref
        cls.stage_new = ref('helpdesk_ticket_management.stage_new')
        cls.stage_progress = ref('helpdesk_ticket_management.stage_in_progress')
        cls.stage_waiting = ref('helpdesk_ticket_management.stage_waiting')
        cls.stage_solved = ref('helpdesk_ticket_management.stage_solved')
        cls.stage_cancelled = ref('helpdesk_ticket_management.stage_cancelled')
        cls.type_incident = ref('helpdesk_ticket_management.type_incident')
        cls.type_question = ref('helpdesk_ticket_management.type_question')
        cls.agent1 = new_test_user(cls.env, 'sd_agent1', groups='helpdesk_ticket_management.group_support_user',
                                   name='Agent One', email='agent1@example.com')
        cls.agent2 = new_test_user(cls.env, 'sd_agent2', groups='helpdesk_ticket_management.group_support_user',
                                   name='Agent Two', email='agent2@example.com')
        cls.leader = new_test_user(cls.env, 'sd_leader', groups='helpdesk_ticket_management.group_support_leader',
                                   name='Team Leader', email='leader@example.com')
        cls.calendar = cls.env['resource.calendar'].create({
            'name': 'Support 9-17 UTC', 'tz': 'UTC',
            'attendance_ids': [(5, 0, 0)] + [(0, 0, {'name': f'Day {d}', 'dayofweek': str(d), 'hour_from': 9,
                                                      'hour_to': 17}) for d in range(5)],
        })
        cls.team = cls.env['support.team'].create({
            'name': 'Level 1', 'member_ids': [(6, 0, (cls.agent1 | cls.agent2).ids)], 'leader_id': cls.leader.id,
            'resource_calendar_id': cls.calendar.id, 'alias_name': 'level1',
        })
        cls.other_team = cls.env['support.team'].create({'name': 'Billing', 'alias_name': 'billing'})
        cls.customer_company = cls.env['res.partner'].create({'name': 'Acme Corp', 'is_company': True,
                                                              'email': 'info@acme.example.com'})
        cls.customer = cls.env['res.partner'].create({'name': 'Jane Customer', 'email': 'jane@acme.example.com',
                                                      'parent_id': cls.customer_company.id, 'phone': '+32 470 12 34 56'})
        cls.other_customer = cls.env['res.partner'].create({'name': 'Bob Other', 'email': 'bob@other.example.com'})

    def _ticket(self, **vals):
        values = {'name': 'Printer does not print', 'team_id': self.team.id, 'partner_id': self.customer.id}
        values.update(vals)
        return self.env['support.ticket'].create(values)
