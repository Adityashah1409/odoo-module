from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestActivityManagement(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.boss = new_test_user(cls.env, 'am_boss', groups='base.group_user,activity_management.group_activity_supervisor',
                                 name='Boss Supervisor')
        cls.alice = new_test_user(cls.env, 'am_alice', groups='base.group_user,base.group_partner_manager',
                                  name='Alice Agent')
        cls.bob = new_test_user(cls.env, 'am_bob', groups='base.group_user,base.group_partner_manager', name='Bob Agent')
        cls.alice.activity_supervisor_id = cls.boss
        cls.partner = cls.env['res.partner'].create({'name': 'Activity Customer'})
        cls.partner2 = cls.env['res.partner'].create({'name': 'Second Customer'})
        cls.todo = cls.env.ref('mail.mail_activity_data_todo')
        cls.call = cls.env.ref('mail.mail_activity_data_call')
        cls.today = fields.Date.context_today(cls.env['mail.activity'])

    def _activity(self, user=None, deadline=None, record=None, **vals):
        record = record or self.partner
        return self.env['mail.activity'].create({
            'res_model_id': self.env['ir.model']._get_id('res.partner'),
            'res_id': record.id,
            'activity_type_id': self.todo.id,
            'summary': vals.pop('summary', 'Follow up'),
            'user_id': (user or self.alice).id,
            'date_deadline': deadline or self.today,
            **vals,
        })

    def test_supervisor_and_progress(self):
        activity = self._activity()
        self.assertEqual(activity.supervisor_id, self.boss, 'supervisor comes from the assignee')
        self.assertEqual(activity.progress, 'open')
        activity.user_id = self.bob
        self.assertFalse(activity.supervisor_id, 'Bob has no supervisor')
        self.assertEqual(self.boss.activity_team_ids, self.alice)

    def test_done_wizard_keeps_history(self):
        activity = self._activity()
        wizard = self.env['activity.done.wizard'].with_user(self.alice).create({
            'activity_ids': [(6, 0, activity.ids)], 'feedback': '<p>Called, all good</p>'})
        wizard.action_done()
        activity = activity.with_context(active_test=False)
        self.assertFalse(activity.active)
        self.assertEqual(activity.progress, 'done')
        self.assertEqual(activity.done_by_id, self.alice)
        self.assertIn('all good', str(activity.feedback))
        self.assertIn(activity, self.env['mail.activity'].with_context(active_test=False).search(
            [('progress', '=', 'done'), ('res_id', '=', self.partner.id)]))

    def test_cancel_with_reason(self):
        activity = self._activity()
        messages_before = self.partner.message_ids
        with self.assertRaises(UserError):
            activity.action_cancel_with_reason('  ')
        self.env['activity.cancel.wizard'].with_user(self.bob).create({
            'activity_ids': [(6, 0, activity.ids)], 'reason': 'Customer already signed'}).action_confirm()
        activity = activity.with_context(active_test=False)
        self.assertEqual(activity.progress, 'cancelled')
        self.assertFalse(activity.active)
        self.assertEqual(activity.cancelled_by_id, self.bob)
        message = self.partner.message_ids - messages_before
        self.assertEqual(len(message), 1)
        self.assertIn('Customer already signed', message.body)
        self.assertEqual(message.partner_ids, self.alice.partner_id | self.boss.partner_id,
                         'assignee and supervisor are notified')
        with self.assertRaises(UserError):
            activity.action_cancel_with_reason('again')
        activity.action_reopen()
        self.assertEqual(activity.progress, 'open')
        self.assertTrue(activity.active)
        self.assertFalse(activity.cancel_reason)

    def test_cancel_without_supervisor_notification(self):
        settings = self.env['res.config.settings'].create({})
        self.assertTrue(settings.activity_notify_supervisor, 'on by default')
        settings.activity_notify_supervisor = False
        settings.execute()
        self.assertFalse(self.env['res.config.settings'].create({}).activity_notify_supervisor,
                         'the setting can be switched off')
        activity = self._activity()
        messages_before = self.partner.message_ids
        activity.with_user(self.bob).action_cancel_with_reason('Not needed')
        self.assertEqual((self.partner.message_ids - messages_before).partner_ids, self.alice.partner_id)

    def test_recurring_activity(self):
        activity = self._activity(recurrence_interval=2, recurrence_unit='weeks', priority='2',
                                  estimated_hours=1.5, deadline=date(2026, 3, 2))
        tag = self.env['mail.activity.tag'].create({'name': 'Weekly'})
        activity.tag_ids = tag
        activity.action_feedback(feedback='done')
        nxt = self.env['mail.activity'].search([('res_id', '=', self.partner.id), ('res_model', '=', 'res.partner')])
        self.assertEqual(len(nxt), 1)
        self.assertEqual(nxt.date_deadline, date(2026, 3, 16))
        self.assertEqual((nxt.priority, nxt.tag_ids, nxt.recurrence_interval, nxt.user_id),
                         ('2', tag, 2, self.alice))

    def test_timer(self):
        activity = self._activity(estimated_hours=2)
        activity.action_timer_start()
        self.assertTrue(activity.timer_start)
        activity.timer_start = fields.Datetime.now() - timedelta(minutes=90)
        activity.action_timer_stop()
        self.assertFalse(activity.timer_start)
        self.assertAlmostEqual(activity.spent_hours, 1.5, places=2)
        self.assertAlmostEqual(activity.remaining_hours, 0.5, places=2)
        activity.action_timer_start()
        activity.timer_start = fields.Datetime.now() - timedelta(minutes=30)
        activity.action_feedback()
        self.assertAlmostEqual(activity.with_context(active_test=False).spent_hours, 2.0, places=2,
                               msg='the timer stops when the activity is done')

    def test_mass_schedule(self):
        partners = self.partner | self.partner2
        wizard = Form(self.env['activity.mass.schedule'].with_context(
            active_model='res.partner', active_ids=partners.ids))
        wizard.activity_type_id = self.call
        wizard.user_ids.clear()
        wizard.user_ids.add(self.alice)
        wizard.user_ids.add(self.bob)
        wizard.date_deadline = self.today + timedelta(days=3)
        wizard.priority = '1'
        wizard = wizard.save()
        self.assertEqual(wizard.record_count, 2)
        self.assertEqual(wizard.summary, self.call.summary or False)
        action = wizard.action_schedule()
        self.assertEqual(action['tag'], 'display_notification')
        activities = self.env['mail.activity'].search([('res_model', '=', 'res.partner'), ('res_id', 'in', partners.ids)])
        self.assertEqual(len(activities), 4)
        self.assertEqual(set(activities.mapped('priority')), {'1'})
        self.assertEqual(activities.filtered(lambda a: a.user_id == self.alice).supervisor_id, self.boss)

    def test_mass_schedule_binding_from_settings(self):
        partner_model = self.env['ir.model']._get('res.partner')
        settings = self.env['res.config.settings'].create({})
        settings.activity_mass_model_ids = [(4, partner_model.id)]
        settings.execute()
        binding = self.env['ir.actions.act_window'].search([
            ('res_model', '=', 'activity.mass.schedule'), ('binding_model_id', '=', partner_model.id)])
        self.assertEqual(len(binding), 1)
        self.assertEqual(self.env['res.config.settings'].create({}).activity_mass_model_ids, partner_model)
        settings = self.env['res.config.settings'].create({})
        settings.activity_mass_model_ids = [(5, 0, 0)]
        settings.execute()
        self.assertFalse(binding.exists())

    def test_reminder_digest(self):
        self.env['ir.config_parameter'].sudo().set_param('activity_management.reminder_enabled', 'True')
        due = self._activity(deadline=self.today + timedelta(days=1), summary='Due tomorrow')
        late = self._activity(deadline=self.today - timedelta(days=4), summary='Late one')
        later = self._activity(deadline=self.today + timedelta(days=10), summary='Much later')
        bob_one = self._activity(user=self.bob, deadline=self.today)
        before = self.env['mail.message'].search([])
        self.env['mail.activity']._cron_send_reminders()
        digests = self.env['mail.message'].search([]) - before
        self.assertEqual(len(digests), 2, 'one digest per user')
        alice_digest = digests.filtered(lambda m: self.alice.partner_id in m.partner_ids)
        self.assertIn('Due tomorrow', alice_digest.body)
        self.assertIn('Late one', alice_digest.body)
        self.assertNotIn('Much later', alice_digest.body)
        self.assertEqual((due | late | bob_one).mapped('reminder_sent_on'), [self.today] * 3)
        self.assertFalse(later.reminder_sent_on)
        before = self.env['mail.message'].search([])
        self.env['mail.activity']._cron_send_reminders()
        self.assertFalse(self.env['mail.message'].search([]) - before, 'once a day only')

    def test_reminder_disabled(self):
        self._activity()
        before = self.env['mail.message'].search([])
        self.env['mail.activity']._cron_send_reminders()
        self.assertFalse(self.env['mail.message'].search([]) - before)

    def test_dashboard_data_and_scopes(self):
        self._activity(deadline=self.today - timedelta(days=1), summary='late')
        self._activity(deadline=self.today, summary='today')
        self._activity(deadline=self.today + timedelta(days=5), summary='planned')
        self._activity(user=self.bob, summary='bob')
        self._activity(summary='to cancel').action_cancel_with_reason('nope')
        self._activity(summary='to close').action_feedback()
        Activity = self.env['mail.activity']
        mine = Activity.with_user(self.alice).get_dashboard_data(scope='all')
        self.assertEqual(mine['counts'], {'overdue': 1, 'today': 1, 'planned': 1, 'done': 1, 'cancelled': 1},
                         'a user without the manager group only sees their own activities')
        self.assertFalse(mine['filters']['can_team'])
        self.assertEqual([a['summary'] for a in mine['activities']], ['late', 'today', 'planned'])
        self.assertTrue(mine['activities'][0]['overdue'])
        team = Activity.with_user(self.boss).get_dashboard_data(scope='team')
        self.assertEqual(team['counts']['today'], 1, "Alice's activity, not Bob's")
        self.assertEqual(team['by_user'], [{'id': self.alice.id, 'name': self.alice.name, 'count': 3}])
        everyone = Activity.get_dashboard_data(scope='all', res_model='res.partner')
        self.assertGreaterEqual(everyone['counts']['today'], 2)
        self.assertIn(['res.partner', 'Contact'], everyone['filters']['models'])
        week = Activity.with_user(self.alice).get_dashboard_data(scope='mine', period='today')
        self.assertEqual(week['counts']['overdue'] + week['counts']['planned'], 0)
        # the KPI domains give the same numbers in the list views
        for key, domain in mine['domains'].items():
            self.assertEqual(Activity.with_user(self.alice).with_context(active_test=False).search_count(domain),
                             mine['counts'][key], key)

    def test_tag_unique(self):
        self.env['mail.activity.tag'].create({'name': 'Hot'})
        from odoo.tools import mute_logger
        with mute_logger('odoo.sql_db'), self.assertRaises(Exception), self.cr.savepoint():
            self.env['mail.activity.tag'].create({'name': 'Hot'})
