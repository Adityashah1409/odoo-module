from datetime import timedelta

from odoo import api, fields, models
from odoo.http import SESSION_LIFETIME


class LoginAsLog(models.Model):
    _name = 'login.as.log'
    _description = 'Login as other user: audit log'
    _order = 'id desc'
    _rec_name = 'target_user_id'

    origin_user_id = fields.Many2one('res.users', string='Done by', required=True, readonly=True, index=True,
                                     ondelete='cascade')
    target_user_id = fields.Many2one('res.users', string='Logged in as', required=True, readonly=True, index=True,
                                     ondelete='cascade')
    reason = fields.Text(readonly=True)
    start = fields.Datetime(default=fields.Datetime.now, required=True, readonly=True)
    end = fields.Datetime(readonly=True)
    duration = fields.Float('Duration', compute='_compute_duration', store=True, aggregator='sum',
                            help='Length of the session, in hours:minutes.')
    state = fields.Selection([('active', 'Active'), ('closed', 'Ended')], default='active', required=True,
                             readonly=True)
    end_reason = fields.Selection([('switch_back', 'Switched back'), ('switch_other', 'Switched to another user'),
                                   ('logout', 'Logged out'), ('timeout', 'Time limit reached'),
                                   ('expired', 'Session expired')], readonly=True)
    ip_address = fields.Char('IP address', readonly=True)
    user_agent = fields.Char(readonly=True)
    target_is_admin = fields.Boolean('Target is administrator', readonly=True)
    target_share = fields.Boolean('Portal user', readonly=True)

    @api.depends('start', 'end')
    def _compute_duration(self):
        for log in self:
            log.duration = (log.end - log.start).total_seconds() / 3600 if log.start and log.end else 0.0

    def _close(self, reason='switch_back'):
        logs = self.filtered(lambda l: l.state == 'active').sudo()
        logs.write({'state': 'closed', 'end': fields.Datetime.now(), 'end_reason': reason})
        # write now: on a read-only request this raises before the session is touched, and the request is
        # replayed with a read/write cursor
        logs.flush_recordset()

    @api.model
    def _cron_close_stale(self):
        """Close log lines whose session cannot be alive any more (time limit or session lifetime passed)."""
        now = fields.Datetime.now()
        stale = self.sudo().search([('state', '=', 'active'),
                                    ('start', '<', now - timedelta(seconds=SESSION_LIFETIME))])
        stale._close('expired')
        minutes = self.env['res.users']._login_as_minutes()
        if minutes:
            # leave a grace period: the session itself switches back on its next request
            late = self.sudo().search([('state', '=', 'active'),
                                       ('start', '<', now - timedelta(minutes=minutes + 60))])
            late._close('timeout')
        return len(stale)
