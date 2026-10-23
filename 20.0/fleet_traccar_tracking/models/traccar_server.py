import logging
import secrets
from datetime import datetime, timedelta, timezone

import requests

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

TIMEOUT = 30
KNOTS_TO_KMH = 1.852


class TraccarError(Exception):
    pass


def parse_time(value):
    """Traccar ISO date ('2026-10-23T10:00:00.000+00:00') -> naive UTC datetime."""
    if not value:
        return False
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0)


def iso(dt):
    return fields.Datetime.to_datetime(dt).strftime('%Y-%m-%dT%H:%M:%SZ')


class TraccarServer(models.Model):
    _name = 'traccar.server'
    _description = 'Traccar Server'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    url = fields.Char("Server URL", required=True, default='https://demo.traccar.org',
                      help="Base URL of the Traccar web server, without /api.")
    auth_type = fields.Selection([('basic', 'User and password'), ('token', 'API token')],
                                default='basic', required=True)
    username = fields.Char(groups='fleet.fleet_group_manager')
    password = fields.Char(groups='fleet.fleet_group_manager')
    token = fields.Char("API token", groups='fleet.fleet_group_manager',
                        help="Traccar › Settings › Preferences › Token.")
    state = fields.Selection([('draft', 'Not connected'), ('connected', 'Connected'), ('error', 'Error')],
                             default='draft', required=True, readonly=True, copy=False)
    server_version = fields.Char(readonly=True)
    last_sync = fields.Datetime(readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)

    auto_link_vehicles = fields.Boolean(
        default=True, help="When importing devices, link them to the vehicle whose license plate equals the device name or identifier.")
    update_odometer = fields.Boolean(
        default=True, help="Log a vehicle odometer reading when Traccar reports a new total distance.")
    keep_history_days = fields.Integer(default=90, help="Position history older than this is deleted.")
    webhook_token = fields.Char(copy=False, readonly=True, groups='fleet.fleet_group_manager',
                                default=lambda self: secrets.token_urlsafe(24))
    webhook_url = fields.Char(compute='_compute_webhook_url', groups='fleet.fleet_group_manager')

    device_ids = fields.One2many('traccar.device', 'server_id')
    device_count = fields.Integer(compute='_compute_device_count')

    def _compute_webhook_url(self):
        base = self.env['ir.config_parameter'].sudo().get_str('web.base.url', '')
        for server in self:
            server.webhook_url = f"{base}/fleet_traccar_tracking/webhook/{server.webhook_token}"

    def _compute_device_count(self):
        counts = dict(self.env['traccar.device']._read_group([('server_id', 'in', self.ids)], ['server_id'], ['__count']))
        for server in self:
            server.device_count = counts.get(server, 0)

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def _request(self, path, params=None, method='GET'):
        """Call the Traccar REST API and return the decoded JSON."""
        self.ensure_one()
        server = self.sudo()
        headers = {'Accept': 'application/json'}
        auth = None
        if server.auth_type == 'token':
            headers['Authorization'] = f"Bearer {server.token or ''}"
        else:
            auth = (server.username or '', server.password or '')
        try:
            response = requests.request(method, f"{server.url.rstrip('/')}/api/{path}", params=params,
                                        headers=headers, auth=auth, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise TraccarError(str(e)) from e
        if response.status_code == 401:
            raise TraccarError(_("Traccar refused the credentials (HTTP 401)."))
        if response.status_code >= 400:
            raise TraccarError(f"HTTP {response.status_code}: {response.text[:200]}")
        return response.json() if response.content else None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_test_connection(self):
        self.ensure_one()
        try:
            info = self._request('server') or {}
            self._request('devices')
        except TraccarError as e:
            # no exception: the error state must be saved
            self.write({'state': 'error', 'last_error': str(e)})
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'type': 'danger', 'sticky': True,
                               'message': _("Could not connect to Traccar: %s", e),
                               'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}
        self.write({'state': 'connected', 'last_error': False, 'server_version': info.get('version')})
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': _("Connected to Traccar %s", info.get('version') or '')}}

    def action_import_devices(self):
        Device = self.env['traccar.device']
        Vehicle = self.env['fleet.vehicle']
        for server in self:
            for data in server._request('devices') or []:
                device = Device.search([('server_id', '=', server.id), ('traccar_id', '=', data['id'])], limit=1)
                values = {
                    'name': data.get('name'), 'unique_id': data.get('uniqueId'),
                    'status': data.get('status') or 'unknown', 'phone': data.get('phone'),
                    'model': data.get('model'), 'category': data.get('category'),
                    'disabled': data.get('disabled', False),
                    'last_update': parse_time(data.get('lastUpdate')),
                }
                if device:
                    device.write(values)
                else:
                    device = Device.create(dict(values, server_id=server.id, traccar_id=data['id']))
                if server.auto_link_vehicles and not device.vehicle_id:
                    keys = [k for k in (device.name, device.unique_id) if k]
                    vehicle = Vehicle.search([('license_plate', 'in', keys)], limit=1)
                    if vehicle and not vehicle.traccar_device_id:
                        device.vehicle_id = vehicle
        return True

    def action_refresh_positions(self):
        for server in self:
            server._refresh_positions()
        return True

    def action_view_devices(self):
        action = self.env['ir.actions.act_window']._for_xml_id('fleet_traccar_tracking.action_traccar_device')
        action['domain'] = [('server_id', '=', self.id)]
        action['context'] = {'default_server_id': self.id}
        return action

    def action_regenerate_token(self):
        for server in self:
            server.webhook_token = secrets.token_urlsafe(24)

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------
    def _refresh_positions(self):
        """Fetch the latest position of every device and update vehicles."""
        self.ensure_one()
        try:
            devices = {d['id']: d for d in self._request('devices') or []}
            positions = self._request('positions') or []
        except TraccarError as e:
            self.write({'state': 'error', 'last_error': str(e)})
            _logger.warning("Traccar refresh failed for %s: %s", self.name, e)
            return 0
        tracked = self.device_ids.filtered('tracking_enabled')
        by_id = {d.traccar_id: d for d in tracked}
        for traccar_id, data in devices.items():
            if traccar_id in by_id:
                by_id[traccar_id].write({'status': data.get('status') or 'unknown',
                                         'last_update': parse_time(data.get('lastUpdate'))})
        count = 0
        for position in positions:
            device = by_id.get(position.get('deviceId'))
            if device:
                device._apply_position(position)
                count += 1
        self.write({'last_sync': fields.Datetime.now(), 'state': 'connected', 'last_error': False})
        return count

    def _import_trips(self, date_from, date_to, devices=None):
        """Import trips of the period (Traccar trips report) for the given devices."""
        self.ensure_one()
        devices = (devices or self.device_ids).filtered(lambda d: d.server_id == self and d.vehicle_id)
        Trip = self.env['traccar.trip']
        created = Trip
        for device in devices:
            trips = self._request('reports/trips', params={
                'deviceId': device.traccar_id, 'from': iso(date_from), 'to': iso(date_to)}) or []
            for trip in trips:
                start = parse_time(trip.get('startTime'))
                if Trip.search_count([('device_id', '=', device.id), ('start_time', '=', start)], limit=1):
                    continue
                created |= Trip.create({
                    'device_id': device.id, 'vehicle_id': device.vehicle_id.id,
                    'start_time': start, 'end_time': parse_time(trip.get('endTime')),
                    'start_address': trip.get('startAddress'), 'end_address': trip.get('endAddress'),
                    'start_latitude': trip.get('startLat'), 'start_longitude': trip.get('startLon'),
                    'end_latitude': trip.get('endLat'), 'end_longitude': trip.get('endLon'),
                    'distance_km': (trip.get('distance') or 0) / 1000.0,
                    'average_speed': (trip.get('averageSpeed') or 0) * KNOTS_TO_KMH,
                    'max_speed': (trip.get('maxSpeed') or 0) * KNOTS_TO_KMH,
                    'driver_name': trip.get('driverName'),
                })
        return created

    @api.model
    def _cron_refresh_positions(self):
        for server in self.search([('state', '=', 'connected')]):
            server._refresh_positions()

    @api.model
    def _cron_import_trips(self):
        now = fields.Datetime.now()
        for server in self.search([('state', '=', 'connected')]):
            try:
                server._import_trips(now - timedelta(days=1), now)
            except TraccarError as e:
                _logger.warning("Traccar trip import failed for %s: %s", server.name, e)

    @api.autovacuum
    def _gc_positions(self):
        for server in self.search([]):
            if server.keep_history_days:
                limit = fields.Datetime.now() - timedelta(days=server.keep_history_days)
                self.env['traccar.position'].search([('device_id.server_id', '=', server.id),
                                                     ('fix_time', '<', limit)]).unlink()
