import re
from datetime import timedelta

from odoo import api, fields, models

MAX_BODY = 4000
SECRET = re.compile(r'("?(?:client_secret|password|token|access_token|api_key)"?\s*[=:]\s*"?)([^"&,\s}]+)', re.I)


def mask(text):
    """Hide secrets in a logged body."""
    return SECRET.sub(r'\1***', text or '')


class RestApiLog(models.Model):
    _name = 'rest.api.log'
    _description = 'REST API request log'
    _order = 'id desc'
    _rec_name = 'path'

    method = fields.Char(readonly=True)
    path = fields.Char(readonly=True, index=True)
    query = fields.Char(readonly=True)
    status = fields.Integer(readonly=True, index=True)
    duration_ms = fields.Integer('Duration (ms)', readonly=True)
    user_id = fields.Many2one('res.users', readonly=True, ondelete='set null', index=True)
    client_id = fields.Many2one('rest.api.client', readonly=True, ondelete='set null')
    endpoint_id = fields.Many2one('rest.api.endpoint', readonly=True, ondelete='set null')
    ip = fields.Char('IP address', readonly=True, index=True)
    user_agent = fields.Char(readonly=True)
    request_body = fields.Text(readonly=True)
    response_body = fields.Text(readonly=True)
    error = fields.Text(readonly=True)
    state = fields.Selection([('ok', 'Success'), ('client_error', 'Client error'), ('server_error', 'Server error')],
                             compute='_compute_state', store=True)

    @api.depends('status')
    def _compute_state(self):
        for log in self:
            log.state = 'ok' if log.status < 400 else ('client_error' if log.status < 500 else 'server_error')

    @api.model
    def _record(self, values, request_body=None, response_body=None):
        """Store one request (bodies only when enabled, truncated and with secrets masked)."""
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_bool('rest_api_gateway.log_bodies'):
            values['request_body'] = mask((request_body or '')[:MAX_BODY])
            values['response_body'] = mask((response_body or '')[:MAX_BODY])
        return self.sudo().create(values)

    @api.model
    def _recent_count(self, user_id, ip, seconds=60):
        since = fields.Datetime.now() - timedelta(seconds=seconds)
        return self.sudo().search_count([('create_date', '>=', since), ('user_id', '=', user_id), ('ip', '=', ip)])

    @api.model
    def _cron_cleanup(self):
        days = (self.env['ir.config_parameter'].sudo().get_int('rest_api_gateway.log_days', 30) or 30)
        self.sudo().search([('create_date', '<', fields.Datetime.now() - timedelta(days=days))]).unlink()
        self.env['rest.api.token'].sudo().search([('expires_at', '<', fields.Datetime.now())]).unlink()
