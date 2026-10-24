import logging
from datetime import timedelta

import requests

from odoo import _, fields, models

_logger = logging.getLogger(__name__)

TIMEOUT = 60
API = 'https://api.powerbi.com/v1.0/myorg'
SCOPE = 'https://analysis.windows.net/powerbi/api/.default'


class PowerBIError(Exception):
    pass


class PowerBIConnection(models.Model):
    """An Azure AD app (service principal) allowed to write in one Power BI workspace."""
    _name = 'powerbi.connection'
    _description = 'Power BI Connection'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    tenant_id = fields.Char("Tenant ID", required=True, groups='powerbi_connector.group_powerbi_manager',
                            help="Microsoft Entra ID (Azure AD) directory (tenant) ID.")
    client_id = fields.Char("Client ID", required=True, groups='powerbi_connector.group_powerbi_manager',
                            help="Application (client) ID of the app registration.")
    client_secret = fields.Char(groups='powerbi_connector.group_powerbi_manager')
    workspace_id = fields.Char("Workspace ID", required=True,
                               help="The Power BI workspace (group) the service principal is a member of.")
    authority_url = fields.Char(default='https://login.microsoftonline.com', required=True,
                                groups='powerbi_connector.group_powerbi_manager')
    state = fields.Selection([('draft', 'Not connected'), ('connected', 'Connected'), ('error', 'Error')],
                             default='draft', required=True, readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)
    access_token = fields.Char(readonly=True, copy=False, groups='base.group_system')
    token_expiry = fields.Datetime(readonly=True, copy=False, groups='base.group_system')
    dataset_ids = fields.One2many('powerbi.dataset', 'connection_id')

    # ------------------------------------------------------------------
    # Authentication and API
    # ------------------------------------------------------------------
    def _get_token(self):
        """Client-credentials token, cached until 5 minutes before it expires."""
        self.ensure_one()
        conn = self.sudo()
        if conn.access_token and conn.token_expiry and conn.token_expiry > fields.Datetime.now() + timedelta(minutes=5):
            return conn.access_token
        url = f"{conn.authority_url.rstrip('/')}/{conn.tenant_id}/oauth2/v2.0/token"
        try:
            response = requests.post(url, timeout=TIMEOUT, data={
                'grant_type': 'client_credentials', 'client_id': conn.client_id,
                'client_secret': conn.client_secret or '', 'scope': SCOPE,
            })
        except requests.RequestException as e:
            raise PowerBIError(str(e)) from e
        payload = response.json() if response.content else {}
        if response.status_code != 200 or 'access_token' not in payload:
            raise PowerBIError(payload.get('error_description') or f"Authentication failed (HTTP {response.status_code}).")
        conn.write({'access_token': payload['access_token'],
                    'token_expiry': fields.Datetime.now() + timedelta(seconds=int(payload.get('expires_in', 3600)))})
        return payload['access_token']

    def _api(self, method, path, payload=None):
        """Call the Power BI REST API inside the connection's workspace."""
        self.ensure_one()
        url = f"{API}/groups/{self.workspace_id}/{path.lstrip('/')}"
        try:
            response = requests.request(method, url, json=payload, timeout=TIMEOUT,
                                        headers={'Authorization': f"Bearer {self._get_token()}"})
        except requests.RequestException as e:
            raise PowerBIError(str(e)) from e
        if response.status_code >= 400:
            try:
                detail = response.json().get('error', {})
                message = detail.get('message') or detail.get('code') or response.text
            except ValueError:
                message = response.text
            raise PowerBIError(f"{method} {path}: HTTP {response.status_code} {message[:300]}")
        return response.json() if response.content else {}

    def action_test_connection(self):
        self.ensure_one()
        try:
            datasets = self._api('GET', 'datasets').get('value', [])
        except PowerBIError as e:
            self.write({'state': 'error', 'last_error': str(e)})
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'type': 'danger', 'sticky': True, 'message': _("Power BI connection failed: %s", e),
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}
        self.write({'state': 'connected', 'last_error': False})
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': _("Connected. %s dataset(s) in the workspace.", len(datasets)),
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}
