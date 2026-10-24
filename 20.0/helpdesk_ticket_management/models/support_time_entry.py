from odoo import api, fields, models


class SupportTimeEntry(models.Model):
    _name = 'support.time.entry'
    _description = 'Time spent on a ticket'
    _order = 'date desc, id desc'

    ticket_id = fields.Many2one('support.ticket', required=True, ondelete='cascade', index=True)
    team_id = fields.Many2one(related='ticket_id.team_id', store=True)
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, index=True)
    date = fields.Date(required=True, default=fields.Date.context_today)
    description = fields.Char()
    start = fields.Datetime(readonly=True)
    stop = fields.Datetime(readonly=True)
    hours = fields.Float()
    running = fields.Boolean(compute='_compute_running', store=True)

    @api.depends('start', 'stop')
    def _compute_running(self):
        for entry in self:
            entry.running = bool(entry.start and not entry.stop)

    def _stop(self):
        now = fields.Datetime.now()
        for entry in self.filtered('running'):
            entry.write({'stop': now, 'hours': entry.hours + (now - entry.start).total_seconds() / 3600})
