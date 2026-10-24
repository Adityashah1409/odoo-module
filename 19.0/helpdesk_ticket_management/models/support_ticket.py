from datetime import datetime, timedelta
from urllib.parse import quote

from markupsafe import Markup

from odoo import api, fields, models, tools
from odoo.exceptions import UserError

from .support_sla import PRIORITIES

PARAM = 'helpdesk_ticket_management.'


class SupportTicket(models.Model):
    _name = 'support.ticket'
    _description = 'Helpdesk ticket'
    _inherit = ['portal.mixin', 'mail.thread.cc', 'mail.activity.mixin', 'rating.mixin',
                'mail.tracking.duration.mixin']
    _order = 'priority desc, id desc'
    _rec_names_search = ['number', 'name', 'partner_name', 'partner_email']
    _track_duration_field = 'stage_id'
    _mail_post_access = 'read'

    number = fields.Char('Reference', readonly=True, copy=False, default='/', index='trigram')
    name = fields.Char('Subject', required=True, tracking=True)
    description = fields.Html()
    active = fields.Boolean(default=True)
    color = fields.Integer()
    channel = fields.Selection([('internal', 'Internal'), ('email', 'E-mail'), ('portal', 'Portal'), ('phone', 'Phone')],
                               default='internal', required=True, string='Source')
    team_id = fields.Many2one('support.team', string='Team', tracking=True, index=True,
                              default=lambda self: self.env['support.team']._get_default_team())
    company_id = fields.Many2one('res.company', compute='_compute_company_id', store=True, readonly=False,
                                 required=True, index=True, default=lambda self: self.env.company)
    user_id = fields.Many2one('res.users', string='Assigned to', tracking=True, index=True,
                              domain=[('share', '=', False)])
    assignee_ids = fields.Many2many('res.users', 'support_ticket_assignee_rel', 'ticket_id', 'user_id',
                                    string='Also assigned', domain=[('share', '=', False)])
    partner_id = fields.Many2one('res.partner', string='Customer', tracking=True, index=True)
    commercial_partner_id = fields.Many2one(related='partner_id.commercial_partner_id', store=True,
                                            string='Customer company')
    partner_name = fields.Char('Customer name', compute='_compute_partner_info', store=True, readonly=False)
    partner_email = fields.Char('E-mail', compute='_compute_partner_info', store=True, readonly=False)
    partner_phone = fields.Char('Phone', compute='_compute_partner_info', store=True, readonly=False)
    stage_id = fields.Many2one(
        'support.stage', string='Stage', tracking=True, index=True, copy=False, ondelete='restrict',
        compute='_compute_stage_id', store=True, readonly=False, group_expand='_read_group_expand_stage_ids',
        domain="['|', ('team_ids', '=', False), ('team_ids', 'in', team_id)]")
    is_closed = fields.Boolean(related='stage_id.is_closed', store=True, index=True, string='Closed')
    priority = fields.Selection(PRIORITIES, default='0', tracking=True, index=True)
    type_id = fields.Many2one('support.ticket.type', string='Type', tracking=True)
    category_id = fields.Many2one('support.category', string='Category', domain=[('parent_id', '=', False)])
    sub_category_id = fields.Many2one('support.category', string='Sub-category',
                                      domain="[('parent_id', '=', category_id)]")
    tag_ids = fields.Many2many('support.tag', string='Tags')

    date_assigned = fields.Datetime('Assigned on', readonly=True, copy=False)
    date_last_stage_update = fields.Datetime('Last stage update', readonly=True, copy=False,
                                             default=fields.Datetime.now)
    date_closed = fields.Datetime('Closed on', readonly=True, copy=False)
    closed_by_id = fields.Many2one('res.users', 'Closed by', readonly=True, copy=False)
    resolution = fields.Html()
    last_reply_by = fields.Selection([('customer', 'Customer'), ('staff', 'Support')], string='Last reply from',
                                     readonly=True, copy=False)
    date_last_customer_reply = fields.Datetime('Last customer reply', readonly=True, copy=False)
    date_last_staff_reply = fields.Datetime('Last support reply', readonly=True, copy=False)
    merged_into_id = fields.Many2one('support.ticket', string='Merged into', readonly=True, copy=False)

    sla_status_ids = fields.One2many('support.ticket.sla', 'ticket_id', string='SLA', copy=False)
    sla_deadline = fields.Datetime('SLA deadline', compute='_compute_sla', store=True, index=True,
                                   help='Earliest deadline of the SLA policies not reached yet.')
    sla_fail = fields.Boolean('SLA failed', compute='_compute_sla', store=True, index=True)

    checklist_template_id = fields.Many2one('support.checklist.template', string='Load checklist', copy=False)
    checklist_ids = fields.One2many('support.ticket.checklist', 'ticket_id', string='Checklist', copy=True)
    checklist_progress = fields.Float('Checklist (%)', compute='_compute_checklist_progress', store=True)
    time_entry_ids = fields.One2many('support.time.entry', 'ticket_id', string='Time spent')
    spent_hours = fields.Float('Hours spent', compute='_compute_spent_hours', store=True)
    timer_running = fields.Boolean(compute='_compute_timer_running', string='My timer is running')
    timer_user_ids = fields.Many2many('res.users', compute='_compute_timer_running', string='Timers running')

    # ------------------------------------------------------------------ computes
    @api.depends('team_id')
    def _compute_company_id(self):
        for ticket in self:
            ticket.company_id = ticket.team_id.company_id or ticket.company_id or self.env.company

    @api.depends('partner_id')
    def _compute_partner_info(self):
        for ticket in self.filtered('partner_id'):
            ticket.partner_name = ticket.partner_id.name
            ticket.partner_email = ticket.partner_id.email
            ticket.partner_phone = ticket.partner_id.phone

    @api.depends('team_id')
    def _compute_stage_id(self):
        for ticket in self:
            stage = ticket.stage_id
            if not stage or (ticket.team_id and stage.team_ids and ticket.team_id not in stage.team_ids):
                ticket.stage_id = ticket._default_stage()

    def _default_stage(self):
        self.ensure_one()
        if self.team_id:
            return self.team_id._get_first_stage()
        return self.env['support.stage'].search([('is_closed', '=', False)], limit=1)

    @api.depends('sla_status_ids.deadline', 'sla_status_ids.status', 'sla_status_ids.reached_datetime')
    def _compute_sla(self):
        for ticket in self:
            open_lines = ticket.sla_status_ids.filtered(lambda s: not s.reached_datetime)
            ticket.sla_deadline = min(open_lines.mapped('deadline')) if open_lines else False
            ticket.sla_fail = any(s.status == 'failed' for s in ticket.sla_status_ids)

    @api.depends('checklist_ids.done')
    def _compute_checklist_progress(self):
        for ticket in self:
            items = ticket.checklist_ids
            ticket.checklist_progress = 100.0 * len(items.filtered('done')) / len(items) if items else 0.0

    @api.depends('time_entry_ids.hours')
    def _compute_spent_hours(self):
        for ticket in self:
            ticket.spent_hours = sum(ticket.time_entry_ids.mapped('hours'))

    @api.depends('time_entry_ids.running', 'time_entry_ids.user_id')
    @api.depends_context('uid')
    def _compute_timer_running(self):
        running = self.env['support.time.entry'].search([('ticket_id', 'in', self.ids), ('running', '=', True)])
        for ticket in self:
            users = running.filtered(lambda e: e.ticket_id == ticket).user_id
            ticket.timer_user_ids = users
            ticket.timer_running = self.env.user in users

    @api.depends('number', 'name')
    def _compute_display_name(self):
        for ticket in self:
            ticket.display_name = f'[{ticket.number}] {ticket.name}' if ticket.number and ticket.number != '/' \
                else ticket.name

    def _compute_access_url(self):
        super()._compute_access_url()
        for ticket in self:
            ticket.access_url = f'/my/tickets/{ticket.id}'

    @api.model
    def _read_group_expand_stage_ids(self, stages, domain):
        team_id = self.env.context.get('default_team_id')
        search_domain = ['|', ('team_ids', '=', False), ('team_ids', 'in', [team_id])] if team_id else []
        return stages.search(search_domain) | stages

    # ------------------------------------------------------------------ CRUD
    @api.model_create_multi
    def create(self, vals_list):
        now = fields.Datetime.now()
        Team = self.env['support.team']
        for vals in vals_list:
            if vals.get('number', '/') == '/':
                vals['number'] = self.env['ir.sequence'].sudo().next_by_code('support.ticket') or '/'
            if vals.get('user_id'):
                vals['date_assigned'] = now
            if not vals.get('stage_id'):
                # explicit stage so the stage e-mail (acknowledgement) is sent on creation
                team = Team.browse(vals['team_id']) if vals.get('team_id') else Team._get_default_team()
                stage = team._get_first_stage() if team else \
                    self.env['support.stage'].search([('is_closed', '=', False)], limit=1)
                if stage:
                    vals['stage_id'] = stage.id
        tickets = super().create(vals_list)
        for ticket in tickets:
            if not ticket.user_id and ticket.team_id and ticket.team_id.assignment_method != 'manual':
                user = ticket.team_id._determine_user()
                if user:
                    ticket.user_id = user
                    ticket.team_id.sudo().last_assigned_user_id = user
            if ticket.partner_id:
                ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
        templates = self.env['support.checklist.template'].search([('type_ids', 'in', tickets.type_id.ids)]) \
            if tickets.type_id else self.env['support.checklist.template']
        for ticket in tickets:
            ticket._load_checklist(templates.filtered(lambda t: ticket.type_id in t.type_ids)
                                   | ticket.checklist_template_id)
        tickets._sla_apply()
        return tickets

    def write(self, vals):
        now = fields.Datetime.now()
        if vals.get('user_id'):
            vals['date_assigned'] = now
        closing = False
        if 'stage_id' in vals:
            stage = self.env['support.stage'].browse(vals['stage_id'])
            vals['date_last_stage_update'] = now
            if stage.is_closed:
                closing = True
                vals.setdefault('date_closed', now)
                vals.setdefault('closed_by_id', self.env.uid)
            else:
                vals.update(date_closed=False, closed_by_id=False)
        res = super().write(vals)
        if 'stage_id' in vals:
            self._sla_reach_stage()
            if closing:
                self.env['support.time.entry'].sudo().search(
                    [('ticket_id', 'in', self.ids), ('running', '=', True)])._stop()
        if {'team_id', 'priority', 'type_id', 'tag_ids', 'partner_id'} & set(vals):
            self._sla_apply()
        if vals.get('checklist_template_id'):
            self._load_checklist(self.env['support.checklist.template'].browse(vals['checklist_template_id']))
        if vals.get('type_id'):
            templates = self.env['support.checklist.template'].search([('type_ids', 'in', [vals['type_id']])])
            self.filtered(lambda t: not t.checklist_ids)._load_checklist(templates)
        if vals.get('partner_id'):
            for ticket in self:
                ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
        return res

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        return [dict(vals, name=self.env._('%s (copy)', ticket.name)) for ticket, vals in zip(self, vals_list)]

    # ------------------------------------------------------------------ SLA
    def _sla_apply(self):
        """Add the statuses of the matching policies; drop the unreached ones that no longer match."""
        policies = self.env['support.sla'].sudo().search([('team_id', 'in', self.team_id.ids),
                                                          ('team_id.use_sla', '=', True)])
        Status = self.env['support.ticket.sla'].sudo()
        values = []
        for ticket in self.sudo():
            current = ticket.sla_status_ids
            current_policies = current.sla_id
            matching = policies.filtered(lambda p: p._matches(ticket)) if not ticket.is_closed else policies.browse()
            dropped = current.filtered(lambda s: s.sla_id not in matching and not s.reached_datetime)
            current_policies -= dropped.sla_id
            dropped.unlink()
            start = ticket.create_date or fields.Datetime.now()
            values += [{'ticket_id': ticket.id, 'sla_id': policy.id, 'deadline': policy._deadline(start)}
                       for policy in matching - current_policies]
        if values:
            Status.create(values)
            self._sla_reach_stage()

    def _sla_reach_stage(self):
        for ticket in self.sudo():
            stage = ticket.stage_id
            if not stage:
                continue
            lines = ticket.sla_status_ids.filtered(
                lambda s: not s.reached_datetime and (
                    stage.is_closed or (stage.sequence, stage.id) >= (s.sla_id.stage_id.sequence, s.sla_id.stage_id.id)))
            lines._reach()

    # ------------------------------------------------------------------ checklist / timer
    def _load_checklist(self, templates):
        Item = self.env['support.ticket.checklist']
        for ticket in self:
            existing = set(ticket.checklist_ids.mapped('name'))
            values = []
            for line in templates.line_ids.sorted(lambda l: (l.template_id.id, l.sequence, l.id)):
                if line.name not in existing:
                    existing.add(line.name)
                    values.append({'ticket_id': ticket.id, 'name': line.name, 'sequence': len(existing) * 10})
            Item.create(values)

    def action_timer_start(self):
        self.ensure_one()
        Entry = self.env['support.time.entry']
        if self.is_closed:
            raise UserError(self.env._('This ticket is closed.'))
        if self.timer_running:
            return True
        if not self.env['ir.config_parameter'].sudo().get_param(PARAM + 'multi_timer'):
            other = Entry.search([('user_id', '=', self.env.uid), ('running', '=', True), ('ticket_id', '!=', self.id)],
                                 limit=1)
            if other:
                raise UserError(self.env._(
                    'Your timer is running on %(ticket)s. Stop it first, or allow several timers in the settings.',
                    ticket=other.ticket_id.display_name))
        Entry.create({'ticket_id': self.id, 'start': fields.Datetime.now(),
                      'description': self.env._('Work on %s', self.number)})
        return True

    def action_timer_stop(self):
        self.env['support.time.entry'].search([('ticket_id', 'in', self.ids), ('user_id', '=', self.env.uid),
                                               ('running', '=', True)])._stop()
        return True

    # ------------------------------------------------------------------ actions
    def action_assign_to_me(self):
        self.write({'user_id': self.env.uid})
        return True

    def action_close(self):
        for ticket in self:
            stage = ticket.team_id._get_close_stage() if ticket.team_id else \
                self.env['support.stage'].search([('is_closed', '=', True)], limit=1)
            if not stage:
                raise UserError(self.env._('No closing stage is configured for this team.'))
            ticket.stage_id = stage
        return True

    def action_open_whatsapp(self):
        self.ensure_one()
        if not self.partner_phone:
            raise UserError(self.env._('The customer has no phone number.'))
        return {
            'type': 'ir.actions.act_window', 'res_model': 'support.whatsapp.wizard', 'view_mode': 'form',
            'views': [(False, 'form')], 'target': 'new', 'name': self.env._('Send by WhatsApp'),
            'context': {'default_ticket_id': self.id},
        }

    def action_open_merge(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': 'support.ticket.merge', 'view_mode': 'form',
            'views': [(False, 'form')], 'target': 'new', 'name': self.env._('Merge tickets'),
            'context': {'active_model': self._name, 'active_ids': self.ids},
        }

    def action_view_sla(self):
        action = self.env['ir.actions.act_window']._for_xml_id('helpdesk_ticket_management.action_support_sla_report')
        action.update({'domain': [('ticket_id', 'in', self.ids)], 'context': {}, 'view_mode': 'list,form',
                       'views': [(False, 'list'), (False, 'form')]})
        return action

    def _whatsapp_url(self, message):
        self.ensure_one()
        digits = ''.join(c for c in (self.partner_phone or '') if c.isdigit())
        return f'https://wa.me/{digits}?text={quote(message or "")}'

    # ------------------------------------------------------------------ mail
    @api.model
    def message_new(self, msg_dict, custom_values=None):
        values = dict(custom_values or {})
        email_from = msg_dict.get('email_from') or ''
        partner = self.env['res.partner'].browse(msg_dict.get('author_id')).exists()
        if not partner and email_from:
            partner = self.env['mail.thread']._partner_find_from_emails_single([email_from], no_create=False)
            msg_dict['author_id'] = partner.id
        values.setdefault('name', msg_dict.get('subject') or self.env._('No subject'))
        values.setdefault('description', msg_dict.get('body'))
        values['channel'] = 'email'
        if partner:
            values.setdefault('partner_id', partner.id)
        else:
            values.setdefault('partner_email', tools.email_normalize(email_from) or email_from)
        return super(SupportTicket, self.with_context(default_user_id=False)).message_new(
            msg_dict, custom_values=values)

    def _message_post_after_hook(self, message, msg_values):
        res = super()._message_post_after_hook(message, msg_values)
        comment = self.env['ir.model.data']._xmlid_to_res_id('mail.mt_comment')
        if message.message_type in ('email', 'comment') and message.subtype_id.id == comment:
            author_users = message.author_id.sudo().user_ids
            self._register_reply('staff' if any(not u.share for u in author_users) else 'customer')
        return res

    def _register_reply(self, who):
        """Remember who answered last and move the stage (support answered -> waiting, customer answered -> in progress)."""
        ICP = self.env['ir.config_parameter'].sudo()
        stage_id = int(ICP.get_param(PARAM + ('staff_reply_stage_id' if who == 'staff' else 'customer_reply_stage_id'))
                       or 0)
        stage = self.env['support.stage'].sudo().browse(stage_id).exists()
        now = fields.Datetime.now()
        for ticket in self.sudo():
            vals = {'last_reply_by': who, f'date_last_{who}_reply': now}
            # customers answering their own first message do not move the ticket; a closed ticket stays closed
            moves = stage and not ticket.is_closed and ticket.stage_id != stage and \
                (who == 'staff' or ticket.last_reply_by == 'staff') and \
                (not stage.team_ids or ticket.team_id in stage.team_ids)
            if moves:
                vals['stage_id'] = stage.id
            ticket.write(vals)

    def _track_template(self, changes):
        res = super()._track_template(changes)
        ticket = self[0]
        if 'stage_id' in changes and ticket.stage_id.template_id and (ticket.partner_id or ticket.partner_email):
            res['stage_id'] = (ticket.stage_id.template_id, {
                'auto_delete_keep_log': False,
                'subtype_id': self.env['ir.model.data']._xmlid_to_res_id('mail.mt_note'),
                'email_layout_xmlid': 'mail.mail_notification_light',
            })
        return res

    def _get_report_base_filename(self):
        self.ensure_one()
        return f'Ticket {self.number}'

    # ------------------------------------------------------------------ crons
    @api.model
    def _cron_auto_close(self):
        now = fields.Datetime.now()
        for team in self.env['support.team'].search([('auto_close_days', '>', 0)]):
            stage = team._get_close_stage()
            if not stage:
                continue
            tickets = self.search([
                ('team_id', '=', team.id), ('is_closed', '=', False), ('last_reply_by', '=', 'staff'),
                ('date_last_staff_reply', '<', now - timedelta(days=team.auto_close_days))])
            for ticket in tickets:
                ticket.stage_id = stage
                ticket.message_post(
                    body=Markup('<p>%s</p>') % self.env._(
                        'Closed automatically: no answer from the customer for %(days)s days.',
                        days=team.auto_close_days),
                    subtype_xmlid='mail.mt_note')

    # ------------------------------------------------------------------ dashboard
    @api.model
    def get_dashboard_data(self, scope='mine', team_id=False):
        """Counters and breakdowns for the dashboard, with the caller's access rights."""
        user = self.env.user
        domain = [('is_closed', '=', False)]
        if scope == 'mine':
            domain += ['|', ('user_id', '=', user.id), ('assignee_ids', 'in', [user.id])]
        elif scope == 'teams':
            domain += ['|', ('team_id.member_ids', 'in', [user.id]), ('team_id.leader_id', '=', user.id)]
        if team_id:
            domain += [('team_id', '=', int(team_id))]
        now = fields.Datetime.now()
        today_start = fields.Datetime.to_datetime(fields.Date.context_today(self))
        team_domain = [('team_id', '=', int(team_id))] if team_id else []
        domains = {
            'open': domain,
            'unassigned': domain + [('user_id', '=', False)],
            'urgent': domain + [('priority', '=', '3')],
            'sla_failed': domain + [('sla_fail', '=', True)],
            'sla_risk': domain + [('sla_fail', '=', False), ('sla_deadline', '!=', False),
                                  ('sla_deadline', '<=', fields.Datetime.to_string(now + timedelta(hours=24)))],
            'closed_today': team_domain + [('is_closed', '=', True),
                                           ('date_closed', '>=', fields.Datetime.to_string(today_start))],
        }
        if scope == 'mine':
            domains['closed_today'] += [('closed_by_id', '=', user.id)]
        counts = {key: self.search_count(dom) for key, dom in domains.items()}
        stages = self._read_group(domain, ['stage_id'], ['__count'])
        by_stage = [{'id': stage.id, 'name': stage.name, 'color': stage.color or '#64748b', 'count': count}
                    for stage, count in sorted(stages, key=lambda g: (g[0].sequence, g[0].id))]
        by_team = [{'id': team.id, 'name': team.name or self.env._('No team'), 'count': count}
                   for team, count in self._read_group(domain, ['team_id'], ['__count'], order='__count desc')]
        by_user = [{'id': u.id, 'name': u.name or self.env._('Unassigned'), 'count': count}
                   for u, count in self._read_group(domain, ['user_id'], ['__count'], order='__count desc', limit=8)]
        by_priority = dict(self._read_group(domain, ['priority'], ['__count']))
        start = today_start - timedelta(days=13)
        created = dict(self.with_context(active_test=False)._read_group(
            team_domain + [('create_date', '>=', fields.Datetime.to_string(start))],
            ['create_date:day'], ['__count']))
        per_day = {}
        for day, count in created.items():
            day = day.date() if isinstance(day, datetime) else day
            per_day[day] = per_day.get(day, 0) + count
        daily = [{'day': fields.Date.to_string((start + timedelta(days=offset)).date()),
                  'count': per_day.get((start + timedelta(days=offset)).date(), 0)} for offset in range(14)]
        ratings = self.env['rating.rating'].sudo().search_read(
            [('res_model', '=', self._name), ('consumed', '=', True), ('rating', '>', 0),
             ('res_id', 'in', self.with_context(active_test=False)._search(team_domain)),
             ('write_date', '>=', fields.Datetime.to_string(now - timedelta(days=30)))], ['rating'])
        tickets = self.search(domain, order='sla_deadline asc, priority desc, id', limit=10)
        return {
            'counts': counts,
            'domains': domains,
            'by_stage': by_stage,
            'by_team': by_team,
            'by_user': by_user,
            'by_priority': [{'key': key, 'name': name, 'count': by_priority.get(key, 0)} for key, name in PRIORITIES],
            'daily': daily,
            'rating': {
                'count': len(ratings),
                'avg': round(sum(r['rating'] for r in ratings) / len(ratings), 1) if ratings else 0,
                'happy': round(100.0 * len([r for r in ratings if r['rating'] >= 4]) / len(ratings)) if ratings else 0,
            },
            'tickets': [{
                'id': t.id, 'number': t.number, 'name': t.name, 'partner': t.partner_name or '',
                'user': t.user_id.name or '', 'stage': t.stage_id.name, 'priority': t.priority,
                'sla_deadline': fields.Datetime.to_string(t.sla_deadline) if t.sla_deadline else False,
                'sla_fail': t.sla_fail,
            } for t in tickets],
            'teams': [{'id': t.id, 'name': t.name} for t in self.env['support.team'].search([])],
            'can_all': user.has_group('helpdesk_ticket_management.group_support_manager'),
        }
