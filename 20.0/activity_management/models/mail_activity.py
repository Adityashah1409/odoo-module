from datetime import timedelta

from dateutil.relativedelta import relativedelta
from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError

PRIORITIES = [('0', 'Normal'), ('1', 'Important'), ('2', 'Urgent')]


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    supervisor_id = fields.Many2one(
        'res.users', string='Supervisor', compute='_compute_supervisor_id', store=True, readonly=False,
        index='btree_not_null', domain=[('share', '=', False)],
        help='Follows the activity: sees it in "My team", is told when it is cancelled.')
    tag_ids = fields.Many2many('mail.activity.tag', string='Tags')
    priority = fields.Selection(PRIORITIES, default='0', required=True)
    progress = fields.Selection([('open', 'Open'), ('done', 'Done'), ('cancelled', 'Cancelled')],
                                compute='_compute_progress', store=True, index=True)
    cancelled = fields.Boolean(readonly=True, copy=False)
    cancel_reason = fields.Text(readonly=True, copy=False)
    cancelled_by_id = fields.Many2one('res.users', readonly=True, copy=False)
    done_by_id = fields.Many2one('res.users', string='Done by', readonly=True, copy=False)
    estimated_hours = fields.Float('Estimated hours')
    spent_hours = fields.Float('Spent hours', copy=False)
    remaining_hours = fields.Float(compute='_compute_remaining_hours')
    timer_start = fields.Datetime(readonly=True, copy=False)
    recurrence_interval = fields.Integer('Repeat every', default=0, help='0 = not recurring.')
    recurrence_unit = fields.Selection(
        [('days', 'Days'), ('weeks', 'Weeks'), ('months', 'Months'), ('years', 'Years')], default='weeks',
        required=True)
    reminder_sent_on = fields.Date(readonly=True, copy=False)

    _recurrence_positive = models.Constraint('CHECK(recurrence_interval >= 0)', 'The recurrence cannot be negative.')

    @api.depends('user_id')
    def _compute_supervisor_id(self):
        for activity in self:
            activity.supervisor_id = activity.user_id.sudo().activity_supervisor_id

    @api.depends('active', 'cancelled')
    def _compute_progress(self):
        for activity in self:
            activity.progress = 'cancelled' if activity.cancelled else ('open' if activity.active else 'done')

    @api.depends('estimated_hours', 'spent_hours')
    def _compute_remaining_hours(self):
        for activity in self:
            activity.remaining_hours = max(activity.estimated_hours - activity.spent_hours, 0.0)

    # ------------------------------------------------------------------ done / cancel
    def _action_done(self, feedback=False, attachment_ids=None):
        recurring = self.filtered(lambda a: a.recurrence_interval > 0 and a.res_model and a.active)
        next_values = [activity._recurrence_next_values() for activity in recurring]
        self._stop_timers()
        self.done_by_id = self.env.user
        messages = super()._action_done(feedback=feedback, attachment_ids=attachment_ids)
        if next_values:
            self.env['mail.activity'].create(next_values)
        return messages

    def _recurrence_next_values(self):
        self.ensure_one()
        return {
            'res_model_id': self.res_model_id.id,
            'res_id': self.res_id,
            'activity_type_id': self.activity_type_id.id,
            'summary': self.summary,
            'note': self.note,
            'user_id': self.user_id.id,
            'supervisor_id': self.supervisor_id.id,
            'tag_ids': [(6, 0, self.tag_ids.ids)],
            'priority': self.priority,
            'estimated_hours': self.estimated_hours,
            'recurrence_interval': self.recurrence_interval,
            'recurrence_unit': self.recurrence_unit,
            'date_deadline': self.date_deadline + relativedelta(**{self.recurrence_unit: self.recurrence_interval}),
        }

    def action_cancel_with_reason(self, reason):
        """Cancel (archive, not delete) with a reason, keep it in the history and tell the people involved."""
        if not (reason or '').strip():
            raise UserError(self.env._('Give a reason to cancel the activity.'))
        if any(not activity.active for activity in self):
            raise UserError(self.env._('Only open activities can be cancelled.'))
        self._stop_timers()
        self.write({'cancelled': True, 'cancel_reason': reason, 'cancelled_by_id': self.env.uid})
        self.action_archive()
        notify_supervisor = self.env['ir.config_parameter'].sudo().get_bool('activity_management.notify_supervisor')
        for activity in self:
            partners = activity.user_id.partner_id
            if notify_supervisor:
                partners |= activity.supervisor_id.partner_id
            partners -= self.env.user.partner_id
            body = Markup('<p>%s</p><p><b>%s</b> %s</p>') % (
                self.env._('Activity "%(name)s" (%(type)s) cancelled by %(user)s.',
                           name=activity.summary or activity.activity_type_id.name,
                           type=activity.activity_type_id.name, user=self.env.user.name),
                self.env._('Reason:'), reason)
            record = activity.res_model and self.env[activity.res_model].sudo().browse(activity.res_id).exists()
            if record and hasattr(record, 'message_post'):
                record.message_post(body=body, partner_ids=partners.ids, subtype_xmlid='mail.mt_note',
                                    author_id=self.env.user.partner_id.id)
            elif partners:
                self.env['mail.thread'].sudo().message_notify(
                    body=body, partner_ids=partners.ids, subject=self.env._('Activity cancelled'))
        return True

    def action_open_cancel_wizard(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': 'activity.cancel.wizard', 'view_mode': 'form',
            'views': [(False, 'form')], 'target': 'new', 'name': self.env._('Cancel activity'),
            'context': {'default_activity_ids': [(6, 0, self.ids)]},
        }

    def action_open_done_wizard(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': 'activity.done.wizard', 'view_mode': 'form',
            'views': [(False, 'form')], 'target': 'new', 'name': self.env._('Mark as done'),
            'context': {'default_activity_ids': [(6, 0, self.ids)]},
        }

    def action_reopen(self):
        """Undo a cancellation."""
        cancelled = self.with_context(active_test=False).filtered('cancelled')
        cancelled.write({'cancelled': False, 'cancel_reason': False, 'cancelled_by_id': False})
        cancelled.action_unarchive()
        return True

    # ------------------------------------------------------------------ timer
    def action_timer_start(self):
        self.filtered(lambda a: not a.timer_start).timer_start = fields.Datetime.now()
        return True

    def action_timer_stop(self):
        self._stop_timers()
        return True

    def _stop_timers(self):
        now = fields.Datetime.now()
        for activity in self.filtered('timer_start'):
            activity.write({'spent_hours': activity.spent_hours + (now - activity.timer_start).total_seconds() / 3600,
                            'timer_start': False})

    # ------------------------------------------------------------------ reminders
    @api.model
    def _cron_send_reminders(self):
        """One digest per user: activities due within N days (and overdue ones), once a day."""
        ICP = self.env['ir.config_parameter'].sudo()
        if not ICP.get_bool('activity_management.reminder_enabled'):
            return
        days = ICP.get_int('activity_management.reminder_days')
        include_overdue = ICP.get_bool('activity_management.overdue_digest')
        today = fields.Date.context_today(self)
        domain = [('active', '=', True), ('user_id', '!=', False), ('date_deadline', '<=', today + timedelta(days=days)),
                  '|', ('reminder_sent_on', '=', False), ('reminder_sent_on', '<', today)]
        if not include_overdue:
            domain.append(('date_deadline', '>=', today))
        activities = self.sudo().search(domain, order='date_deadline, id')
        for user, user_activities in activities.grouped('user_id').items():
            rows = Markup('').join(
                Markup('<tr><td style="padding:4px 8px">%s</td><td style="padding:4px 8px">%s</td>'
                       '<td style="padding:4px 8px">%s</td><td style="padding:4px 8px;color:%s">%s</td></tr>') % (
                    a.activity_type_id.name or '', a.summary or '', a.res_name or '',
                    '#dc2626' if a.date_deadline < today else '#111827', a.date_deadline)
                for a in user_activities)
            overdue = len(user_activities.filtered(lambda a: a.date_deadline < today))
            body = Markup('<p>%s</p><table style="border-collapse:collapse">'
                          '<tr><th style="text-align:left;padding:4px 8px">%s</th><th style="text-align:left;padding:4px 8px">%s</th>'
                          '<th style="text-align:left;padding:4px 8px">%s</th><th style="text-align:left;padding:4px 8px">%s</th></tr>'
                          '%s</table>') % (
                self.env._('You have %(count)s activities to do (%(overdue)s overdue).',
                           count=len(user_activities), overdue=overdue),
                self.env._('Type'), self.env._('Summary'), self.env._('Document'), self.env._('Due'), rows)
            self.env['mail.thread'].sudo().message_notify(
                body=body, partner_ids=user.partner_id.ids,
                subject=self.env._('Your activities: %(count)s to do', count=len(user_activities)))
            user_activities.reminder_sent_on = today

    # ------------------------------------------------------------------ dashboard
    @api.model
    def _dashboard_scope_domain(self, scope):
        user = self.env.user
        if scope == 'all' and user.has_group('activity_management.group_activity_manager'):
            return []
        if scope == 'team' and user.has_group('activity_management.group_activity_supervisor'):
            return ['|', '|', ('user_id', '=', user.id), ('supervisor_id', '=', user.id),
                    ('user_id.activity_supervisor_id', '=', user.id)]
        return [('user_id', '=', user.id)]

    @api.model
    def get_dashboard_data(self, scope='mine', period='all', user_id=False, activity_type_id=False, res_model=False,
                           tag_id=False, limit=50):
        """Counters, breakdowns and a list of activities for the dashboard (with the caller's access rights)."""
        today = fields.Date.context_today(self)
        today_s = fields.Date.to_string(today)
        domain = self._dashboard_scope_domain(scope)
        if user_id:
            domain += [('user_id', '=', int(user_id))]
        if activity_type_id:
            domain += [('activity_type_id', '=', int(activity_type_id))]
        if res_model:
            domain += [('res_model', '=', res_model)]
        if tag_id:
            domain += [('tag_ids', 'in', [int(tag_id)])]
        periods = {
            'today': (today, today),
            'week': (today - timedelta(days=today.weekday()), today + timedelta(days=6 - today.weekday())),
            'month': (today.replace(day=1), today.replace(day=1) + relativedelta(months=1, days=-1)),
            'last30': (today - timedelta(days=30), today),
        }
        if period in periods:
            start, end = periods[period]
            domain += [('date_deadline', '>=', fields.Date.to_string(start)),
                       ('date_deadline', '<=', fields.Date.to_string(end))]
        Activity = self.with_context(active_test=False)
        open_domain = domain + [('progress', '=', 'open')]
        counts = {
            'overdue': Activity.search_count(open_domain + [('date_deadline', '<', today_s)]),
            'today': Activity.search_count(open_domain + [('date_deadline', '=', today_s)]),
            'planned': Activity.search_count(open_domain + [('date_deadline', '>', today_s)]),
            'done': Activity.search_count(domain + [('progress', '=', 'done')]),
            'cancelled': Activity.search_count(domain + [('progress', '=', 'cancelled')]),
        }
        by_type = [{'id': atype.id, 'name': atype.name, 'count': count}
                   for atype, count in Activity._read_group(open_domain, ['activity_type_id'], ['__count'],
                                                            order='__count desc')]
        by_user = [{'id': user.id, 'name': user.name, 'count': count}
                   for user, count in Activity._read_group(open_domain, ['user_id'], ['__count'],
                                                           order='__count desc', limit=8)]
        activities = Activity.search(open_domain, order='date_deadline, priority desc, id', limit=limit)
        user = self.env.user
        return {
            'counts': counts,
            'domains': {
                'overdue': open_domain + [('date_deadline', '<', today_s)],
                'today': open_domain + [('date_deadline', '=', today_s)],
                'planned': open_domain + [('date_deadline', '>', today_s)],
                'done': domain + [('progress', '=', 'done')],
                'cancelled': domain + [('progress', '=', 'cancelled')],
            },
            'by_type': by_type,
            'by_user': by_user,
            'activities': [{
                'id': a.id, 'summary': a.summary or a.activity_type_id.name, 'type': a.activity_type_id.name,
                'icon': a.activity_type_id.icon or 'task_alt', 'document': a.res_name or '', 'res_model': a.res_model,
                'res_id': a.res_id, 'user': a.user_id.name or '', 'supervisor': a.supervisor_id.name or '',
                'deadline': fields.Date.to_string(a.date_deadline), 'overdue': a.date_deadline < today,
                'due_today': a.date_deadline == today, 'priority': a.priority,
                'tags': [{'name': t.name, 'color': t.color} for t in a.tag_ids],
            } for a in activities],
            'filters': {
                'can_team': user.has_group('activity_management.group_activity_supervisor'),
                'can_all': user.has_group('activity_management.group_activity_manager'),
                'types': [{'id': t.id, 'name': t.name} for t in self.env['mail.activity.type'].search([])],
                'tags': [{'id': t.id, 'name': t.name} for t in self.env['mail.activity.tag'].search([])],
                'models': sorted(([model, self.env['ir.model']._get(model).name] for model, _count in
                                  Activity._read_group(domain + [('res_model', '!=', False)], ['res_model'],
                                                       ['__count'])), key=lambda m: m[1] or ''),
                'users': [{'id': u.id, 'name': u.name} for u in
                          (self.env['res.users'].search([('share', '=', False)]) if scope != 'mine' else user)],
            },
        }
