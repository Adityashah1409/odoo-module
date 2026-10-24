from datetime import timedelta, timezone

from odoo import api, fields, models

PRIORITIES = [('0', 'Low'), ('1', 'Medium'), ('2', 'High'), ('3', 'Urgent')]


class SupportSla(models.Model):
    _name = 'support.sla'
    _description = 'SLA policy'
    _order = 'team_id, sequence, id'

    name = fields.Char(required=True, translate=True)
    description = fields.Text(translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    team_id = fields.Many2one('support.team', required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='team_id.company_id', store=True)
    priority = fields.Selection(PRIORITIES, string='Minimum priority', default='0', required=True,
                                help='Applies to tickets of this priority or higher.')
    type_ids = fields.Many2many('support.ticket.type', string='Ticket types', help='Empty = every type.')
    tag_ids = fields.Many2many('support.tag', string='Tags', help='Applies to tickets having one of these tags. Empty = any.')
    partner_ids = fields.Many2many('res.partner', string='Customers',
                                   help='Applies to these customers (and their contacts). Empty = everybody.')
    stage_id = fields.Many2one('support.stage', string='Target stage', required=True,
                               help='The ticket must reach this stage (or a later one) before the deadline.')
    time = fields.Float('Within (working hours)', required=True, default=8.0,
                        help="Counted on the team's working hours.")
    status_count = fields.Integer(compute='_compute_status_count', string='Tickets')
    failed_rate = fields.Float(compute='_compute_status_count', string='Failed (%)')

    def _compute_status_count(self):
        groups = self.env['support.ticket.sla']._read_group(
            [('sla_id', 'in', self.ids)], ['sla_id', 'status'], ['__count'])
        totals, failed = {}, {}
        for sla, status, count in groups:
            totals[sla] = totals.get(sla, 0) + count
            if status == 'failed':
                failed[sla] = count
        for sla in self:
            sla.status_count = totals.get(sla, 0)
            sla.failed_rate = 100.0 * failed.get(sla, 0) / totals[sla] if totals.get(sla) else 0.0

    def _matches(self, ticket):
        self.ensure_one()
        return (ticket.team_id == self.team_id
                and int(ticket.priority or 0) >= int(self.priority)
                and (not self.type_ids or ticket.type_id in self.type_ids)
                and (not self.tag_ids or bool(ticket.tag_ids & self.tag_ids))
                and (not self.partner_ids or ticket.partner_id.commercial_partner_id in self.partner_ids
                     or ticket.partner_id in self.partner_ids))

    def _deadline(self, start):
        """Deadline from ``start`` (naive UTC) after ``time`` working hours of the team."""
        self.ensure_one()
        calendar = self.team_id.resource_calendar_id
        if calendar:
            deadline = calendar.plan_hours(self.time, start.replace(tzinfo=timezone.utc), compute_leaves=True)
            if deadline:
                return deadline.astimezone(timezone.utc).replace(tzinfo=None)
        return start + timedelta(hours=self.time)

    def action_view_status(self):
        action = self.env['ir.actions.act_window']._for_xml_id('helpdesk_ticket_management.action_support_sla_report')
        action['domain'] = [('sla_id', 'in', self.ids)]
        action['context'] = {}
        return action


class SupportTicketSla(models.Model):
    _name = 'support.ticket.sla'
    _description = 'SLA status of a ticket'
    _order = 'deadline, id'
    _rec_name = 'sla_id'

    ticket_id = fields.Many2one('support.ticket', required=True, index=True, ondelete='cascade')
    sla_id = fields.Many2one('support.sla', string='SLA policy', required=True, index=True, ondelete='cascade')
    stage_id = fields.Many2one(related='sla_id.stage_id', string='Target stage')
    team_id = fields.Many2one(related='ticket_id.team_id', store=True, string='Team')
    user_id = fields.Many2one(related='ticket_id.user_id', store=True, string='Assigned to')
    priority = fields.Selection(related='ticket_id.priority', store=True)
    company_id = fields.Many2one(related='ticket_id.company_id', store=True)
    deadline = fields.Datetime(required=True)
    reached_datetime = fields.Datetime('Reached on', readonly=True)
    status = fields.Selection([('ongoing', 'Ongoing'), ('reached', 'Reached'), ('failed', 'Failed')],
                              default='ongoing', required=True, index=True)
    exceeded_hours = fields.Float('Late by (hours)', compute='_compute_exceeded_hours', store=True)

    _ticket_sla_uniq = models.Constraint('UNIQUE(ticket_id, sla_id)', 'A policy applies once per ticket.')

    @api.depends('deadline', 'reached_datetime')
    def _compute_exceeded_hours(self):
        for line in self:
            if line.reached_datetime and line.deadline and line.reached_datetime > line.deadline:
                line.exceeded_hours = (line.reached_datetime - line.deadline).total_seconds() / 3600
            else:
                line.exceeded_hours = 0.0

    def _reach(self, when=None):
        when = when or fields.Datetime.now()
        for line in self.filtered(lambda l: not l.reached_datetime):
            line.write({'reached_datetime': when, 'status': 'reached' if when <= line.deadline else 'failed'})

    @api.model
    def _cron_check_deadlines(self):
        """Ongoing statuses past their deadline become failed (they stay failed when reached late)."""
        self.search([('status', '=', 'ongoing'), ('deadline', '<', fields.Datetime.now())]).write({'status': 'failed'})
