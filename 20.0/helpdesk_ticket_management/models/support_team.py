import ast

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SupportTeam(models.Model):
    _name = 'support.team'
    _description = 'Helpdesk team'
    _inherit = ['mail.alias.mixin', 'mail.thread']
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer()
    description = fields.Html(translate=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company, index=True)
    is_default = fields.Boolean('Default team', help='Tickets created without a team go to this team.')
    leader_id = fields.Many2one('res.users', string='Team leader', domain=[('share', '=', False)], tracking=True)
    member_ids = fields.Many2many('res.users', 'support_team_member_rel', 'team_id', 'user_id', string='Members',
                                  domain=[('share', '=', False)])
    resource_calendar_id = fields.Many2one(
        'resource.calendar', string='Working hours', default=lambda self: self.env.company.resource_calendar_id,
        help='SLA deadlines count only these working hours (public holidays included).')
    assignment_method = fields.Selection([
        ('manual', 'Manual'),
        ('balanced', 'Balanced (fewest open tickets)'),
        ('round_robin', 'Round robin'),
    ], default='manual', required=True, tracking=True)
    last_assigned_user_id = fields.Many2one('res.users', readonly=True, copy=False)
    use_sla = fields.Boolean('SLA policies', default=True)
    use_rating = fields.Boolean('Customer ratings', default=True,
                                help='The e-mail of the closing stage asks the customer to rate the support.')
    auto_close_days = fields.Integer(
        'Auto-close after (days)', default=0,
        help='Close tickets waiting on the customer when they did not answer for this many days. 0 = never.')
    stage_ids = fields.Many2many('support.stage', compute='_compute_stage_ids', string='Stages')
    ticket_ids = fields.One2many('support.ticket', 'team_id')
    open_ticket_count = fields.Integer(compute='_compute_counts')
    unassigned_ticket_count = fields.Integer(compute='_compute_counts')
    urgent_ticket_count = fields.Integer(compute='_compute_counts')
    sla_failed_ticket_count = fields.Integer(compute='_compute_counts')
    sla_count = fields.Integer(compute='_compute_sla_count')

    @api.constrains('is_default', 'company_id')
    def _check_single_default(self):
        for team in self.filtered('is_default'):
            if self.search_count([('is_default', '=', True), ('company_id', '=', team.company_id.id),
                                  ('id', '!=', team.id)]):
                raise ValidationError(self.env._('There can be only one default team per company.'))

    def _compute_stage_ids(self):
        stages = self.env['support.stage'].search([])
        for team in self:
            team.stage_ids = stages.filtered(lambda s: not s.team_ids or team in s.team_ids)

    def _compute_counts(self):
        Ticket = self.env['support.ticket']
        base = [('team_id', 'in', self.ids), ('is_closed', '=', False)]
        counts = {
            'open_ticket_count': dict(Ticket._read_group(base, ['team_id'], ['__count'])),
            'unassigned_ticket_count': dict(Ticket._read_group(base + [('user_id', '=', False)], ['team_id'], ['__count'])),
            'urgent_ticket_count': dict(Ticket._read_group(base + [('priority', '=', '3')], ['team_id'], ['__count'])),
            'sla_failed_ticket_count': dict(Ticket._read_group(base + [('sla_fail', '=', True)], ['team_id'], ['__count'])),
        }
        for team in self:
            for field, values in counts.items():
                team[field] = values.get(team, 0)

    def _compute_sla_count(self):
        counts = dict(self.env['support.sla']._read_group([('team_id', 'in', self.ids)], ['team_id'], ['__count']))
        for team in self:
            team.sla_count = counts.get(team, 0)

    # ------------------------------------------------------------------ mail alias
    def _alias_get_creation_values(self):
        values = super()._alias_get_creation_values()
        values['alias_model_id'] = self.env['ir.model']._get('support.ticket').id
        if self.id:
            values['alias_defaults'] = defaults = ast.literal_eval(self.alias_defaults or '{}')
            defaults['team_id'] = self.id
        return values

    # ------------------------------------------------------------------ business
    @api.model
    def _get_default_team(self, company=None):
        company = company or self.env.company
        return self.search([('is_default', '=', True), ('company_id', '=', company.id)], limit=1) or \
            self.search([('company_id', '=', company.id)], limit=1)

    def _get_first_stage(self):
        self.ensure_one()
        return self.stage_ids.filtered(lambda s: not s.is_closed)[:1] or self.stage_ids[:1]

    def _get_close_stage(self):
        self.ensure_one()
        return self.stage_ids.filtered('is_closed')[:1]

    def _determine_user(self):
        """User the next ticket goes to, following the assignment method (members only)."""
        self.ensure_one()
        members = self.member_ids.filtered(lambda u: u.active).sorted('id')
        if self.assignment_method == 'manual' or not members:
            return self.env['res.users']
        if self.assignment_method == 'balanced':
            open_counts = dict(self.env['support.ticket'].sudo()._read_group(
                [('team_id', '=', self.id), ('is_closed', '=', False), ('user_id', 'in', members.ids)],
                ['user_id'], ['__count']))
            return min(members, key=lambda u: (open_counts.get(u, 0), u.id))
        previous = self.last_assigned_user_id
        following = members.filtered(lambda u: u.id > previous.id) if previous in members else members
        return following[:1] or members[:1]

    # ------------------------------------------------------------------ actions
    def _action_tickets(self, domain, name):
        action = self.env['ir.actions.act_window']._for_xml_id('helpdesk_ticket_management.action_support_ticket')
        action.update({
            'name': name,
            'domain': [('team_id', '=', self.id)] + domain,
            'context': {'default_team_id': self.id},
        })
        return action

    def action_view_open_tickets(self):
        return self._action_tickets([('is_closed', '=', False)], self.env._('Open tickets'))

    def action_view_unassigned_tickets(self):
        return self._action_tickets([('is_closed', '=', False), ('user_id', '=', False)], self.env._('Unassigned'))

    def action_view_urgent_tickets(self):
        return self._action_tickets([('is_closed', '=', False), ('priority', '=', '3')], self.env._('Urgent'))

    def action_view_failed_tickets(self):
        return self._action_tickets([('is_closed', '=', False), ('sla_fail', '=', True)], self.env._('SLA failed'))

    def action_view_slas(self):
        action = self.env['ir.actions.act_window']._for_xml_id('helpdesk_ticket_management.action_support_sla')
        action.update({'domain': [('team_id', '=', self.id)], 'context': {'default_team_id': self.id}})
        return action
