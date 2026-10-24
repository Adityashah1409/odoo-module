from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .common import SupportCommon


@tagged('post_install', '-at_install')
class TestWizards(SupportCommon):

    def test_merge(self):
        first = self._ticket(name='Cannot log in', tag_ids=[(0, 0, {'name': 'Login'})])
        second = self._ticket(name='Login again', priority='2', partner_id=self.other_customer.id)
        second.message_post(body='Second message', message_type='comment', subtype_xmlid='mail.mt_comment')
        second.checklist_ids = [(0, 0, {'name': 'Reset password'})]
        self.env['support.time.entry'].create({'ticket_id': second.id, 'hours': 1.5})
        attachment = self.env['ir.attachment'].create({'name': 'log.txt', 'raw': b'error',
                                                       'res_model': 'support.ticket', 'res_id': second.id})
        wizard = self.env['support.ticket.merge'].with_context(
            active_model='support.ticket', active_ids=(first | second).ids).create({})
        self.assertEqual(wizard.target_id, first, 'the oldest is kept by default')
        self.assertIn('different customers', wizard.warning)
        action = wizard.action_merge()
        self.assertEqual(action['res_id'], first.id)
        self.assertFalse(second.active)
        self.assertTrue(second.is_closed)
        self.assertEqual(second.merged_into_id, first)
        self.assertIn('Second message', first.message_ids.mapped('body').__str__())
        self.assertEqual(attachment.res_id, first.id)
        self.assertEqual(first.checklist_ids.mapped('name'), ['Reset password'])
        self.assertEqual(first.spent_hours, 1.5)
        self.assertEqual(first.priority, '2')
        self.assertIn('Login again', str(first.description))
        self.assertIn(self.other_customer, first.message_partner_ids)
        with self.assertRaises(UserError):
            self.env['support.ticket.merge'].create({'ticket_ids': [(6, 0, first.ids)], 'target_id': first.id}).action_merge()

    def test_mass_update(self):
        tickets = self._ticket() | self._ticket(name='Two') | self._ticket(name='Three', tag_ids=[(0, 0, {'name': 'Old'})])
        old_tag = tickets[2].tag_ids
        new_tag = self.env['support.tag'].create({'name': 'Hardware'})
        wizard = Form(self.env['support.ticket.mass.update'].with_context(active_ids=tickets.ids))
        wizard.user_id = self.agent2
        wizard.priority = '2'
        wizard.stage_id = self.stage_progress
        wizard.add_tag_ids.add(new_tag)
        wizard.remove_tag_ids.add(old_tag)
        wizard.follower_ids.add(self.other_customer)
        wizard = wizard.save()
        self.assertEqual(wizard.ticket_count, 3)
        wizard.action_apply()
        self.assertEqual(set(tickets.mapped('user_id')), {self.agent2})
        self.assertEqual(set(tickets.mapped('priority')), {'2'})
        self.assertEqual(set(tickets.mapped('stage_id')), {self.stage_progress})
        self.assertEqual(tickets.tag_ids, new_tag)
        self.assertTrue(all(self.other_customer in t.message_partner_ids for t in tickets))
        with self.assertRaises(UserError):
            self.env['support.ticket.mass.update'].create({'ticket_ids': [(6, 0, tickets.ids)]}).action_apply()
        self.env['support.ticket.mass.update'].create({'ticket_ids': [(6, 0, tickets.ids)], 'unassign': True}).action_apply()
        self.assertFalse(tickets.user_id)
