import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import api, fields, models


def _hash(value):
    return hashlib.sha256((value or '').encode()).hexdigest()


class RestApiClient(models.Model):
    _name = 'rest.api.client'
    _description = 'REST API OAuth2 client'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    client_id = fields.Char('Client ID', required=True, readonly=True, copy=False,
                            default=lambda self: secrets.token_hex(12))
    secret_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    has_secret = fields.Boolean(compute='_compute_has_secret')
    user_id = fields.Many2one(
        'res.users', string='Run as', required=True, ondelete='restrict',
        domain=[('share', '=', False)], default=lambda self: self.env.user,
        help='Requests made with this client\'s tokens run with the access rights of this user.')
    model_ids = fields.Many2many(
        'ir.model', string='Allowed models',
        help='Leave empty to allow every model the user can access.')
    read_only = fields.Boolean(help='Only GET requests and read methods.')
    token_lifetime = fields.Integer('Token lifetime (s)', default=3600)
    token_ids = fields.One2many('rest.api.token', 'client_id', string='Tokens')
    active_token_count = fields.Integer(compute='_compute_active_token_count')
    last_used = fields.Datetime(readonly=True)
    note = fields.Text()

    _client_id_uniq = models.Constraint('UNIQUE(client_id)', 'The client ID must be unique.')
    _lifetime_positive = models.Constraint('CHECK(token_lifetime > 0)', 'The token lifetime must be positive.')

    def _compute_has_secret(self):
        for client in self.sudo():
            client.has_secret = bool(client.secret_hash)

    @api.depends('token_ids.expires_at')
    def _compute_active_token_count(self):
        now = fields.Datetime.now()
        for client in self:
            client.active_token_count = len(client.token_ids.filtered(lambda t: t.expires_at > now))

    def action_generate_secret(self):
        """Create a new secret, store its hash and show it once."""
        self.ensure_one()
        secret = secrets.token_urlsafe(32)
        self.sudo().secret_hash = _hash(secret)
        self.token_ids.unlink()
        wizard = self.env['rest.api.secret.wizard'].create({'client_id': self.id, 'secret': secret})
        return {
            'type': 'ir.actions.act_window', 'res_model': 'rest.api.secret.wizard', 'res_id': wizard.id,
            'view_mode': 'form', 'target': 'new', 'name': self.env._('Client secret'),
        }

    def action_revoke_tokens(self):
        self.token_ids.unlink()
        return True

    def _check_secret(self, secret):
        self.ensure_one()
        stored = self.sudo().secret_hash
        return bool(stored and secret) and hmac.compare_digest(stored, _hash(secret))

    def _issue_token(self):
        """Return (raw token, lifetime in seconds)."""
        self.ensure_one()
        raw = secrets.token_urlsafe(32)
        self.env['rest.api.token'].sudo().create({
            'client_id': self.id,
            'token_hash': _hash(raw),
            'expires_at': fields.Datetime.now() + timedelta(seconds=self.token_lifetime),
        })
        self.sudo().last_used = fields.Datetime.now()
        return raw, self.token_lifetime

    def _allows(self, model_name, write):
        self.ensure_one()
        if write and self.read_only:
            return False
        return not self.model_ids or model_name in self.model_ids.mapped('model')


class RestApiToken(models.Model):
    _name = 'rest.api.token'
    _description = 'REST API access token'
    _order = 'expires_at desc'
    _rec_name = 'client_id'

    client_id = fields.Many2one('rest.api.client', required=True, ondelete='cascade', index=True)
    token_hash = fields.Char(required=True, index=True)
    expires_at = fields.Datetime(required=True)

    @api.model
    def _find(self, raw):
        """Valid token for a raw bearer value, or an empty recordset (tokens are stored hashed)."""
        if not raw:
            return self.browse()
        return self.sudo().search([('token_hash', '=', _hash(raw)), ('expires_at', '>', fields.Datetime.now()),
                                   ('client_id.active', '=', True)], limit=1)

    def action_revoke(self):
        self.unlink()
        return True


class RestApiSecretWizard(models.TransientModel):
    _name = 'rest.api.secret.wizard'
    _description = 'Show a new client secret once'

    client_id = fields.Many2one('rest.api.client', readonly=True)
    secret = fields.Char(readonly=True)
