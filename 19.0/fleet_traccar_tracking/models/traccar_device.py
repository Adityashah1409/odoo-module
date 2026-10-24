import json

from odoo import _, api, fields, models

from .traccar_server import KNOTS_TO_KMH, parse_time

MOVING_SPEED_KMH = 3.0


class TraccarDevice(models.Model):
    _name = 'traccar.device'
    _description = 'Traccar Device'
    _order = 'name, id'

    name = fields.Char(required=True)
    server_id = fields.Many2one('traccar.server', required=True, ondelete='cascade', index=True)
    traccar_id = fields.Integer("Traccar ID", required=True)
    unique_id = fields.Char("Identifier", help="IMEI or the identifier configured in the Traccar client app.")
    vehicle_id = fields.Many2one('fleet.vehicle', ondelete='set null', index=True)
    tracking_enabled = fields.Boolean(default=True)
    status = fields.Selection([('online', 'Online'), ('offline', 'Offline'), ('unknown', 'Unknown')],
                              default='unknown', readonly=True)
    disabled = fields.Boolean("Disabled in Traccar", readonly=True)
    phone = fields.Char()
    model = fields.Char()
    category = fields.Char()
    last_update = fields.Datetime(readonly=True)
    last_position_id = fields.Integer(readonly=True, help="Traccar id of the last position applied.")
    position_count = fields.Integer(compute='_compute_counts')
    trip_count = fields.Integer(compute='_compute_counts')

    _traccar_uniq = models.Constraint('UNIQUE(server_id, traccar_id)', "Device already imported.")
    _vehicle_uniq = models.UniqueIndex('(vehicle_id) WHERE vehicle_id IS NOT NULL',
                                       "A vehicle can only be linked to one tracking device.")

    def write(self, vals):
        result = super().write(vals)
        if vals.get('status') == 'offline':
            self.vehicle_id.write({'gps_motion_state': 'offline'})
        return result

    def _compute_counts(self):
        positions = dict(self.env['traccar.position']._read_group([('device_id', 'in', self.ids)], ['device_id'], ['__count']))
        trips = dict(self.env['traccar.trip']._read_group([('device_id', 'in', self.ids)], ['device_id'], ['__count']))
        for device in self:
            device.position_count = positions.get(device, 0)
            device.trip_count = trips.get(device, 0)

    def _apply_position(self, data):
        """Store a Traccar position and update the linked vehicle's live fields."""
        self.ensure_one()
        if data.get('id') and data['id'] == self.last_position_id:
            return False
        attributes = data.get('attributes') or {}
        speed = (data.get('speed') or 0.0) * KNOTS_TO_KMH
        moving = attributes.get('motion') if 'motion' in attributes else speed > MOVING_SPEED_KMH
        fix_time = parse_time(data.get('fixTime') or data.get('deviceTime') or data.get('serverTime'))
        position = self.env['traccar.position'].create({
            'device_id': self.id,
            'vehicle_id': self.vehicle_id.id,
            'traccar_id': data.get('id'),
            'fix_time': fix_time or fields.Datetime.now(),
            'latitude': data.get('latitude'),
            'longitude': data.get('longitude'),
            'speed': speed,
            'course': data.get('course'),
            'altitude': data.get('altitude'),
            'accuracy': data.get('accuracy'),
            'battery_level': attributes.get('batteryLevel'),
            'address': data.get('address'),
            'moving': bool(moving),
            'attributes': json.dumps(attributes) if attributes else False,
        })
        self.last_position_id = data.get('id') or 0
        vehicle = self.vehicle_id
        if vehicle:
            vehicle.write({
                'gps_latitude': position.latitude,
                'gps_longitude': position.longitude,
                'gps_speed': speed,
                'gps_fix_time': position.fix_time,
                'gps_accuracy': position.accuracy,
                'gps_battery_level': position.battery_level,
                'gps_address': position.address or False,
                'gps_motion_state': 'offline' if self.status == 'offline' else ('moving' if moving else 'stopped'),
            })
            total = attributes.get('totalDistance') or attributes.get('odometer')
            if total and self.server_id.update_odometer:
                vehicle._gps_update_odometer(total / 1000.0, position.fix_time)
        return position

    def action_view_positions(self):
        action = self.env['ir.actions.act_window']._for_xml_id('fleet_traccar_tracking.action_traccar_position')
        action['domain'] = [('device_id', '=', self.id)]
        return action

    def action_view_trips(self):
        action = self.env['ir.actions.act_window']._for_xml_id('fleet_traccar_tracking.action_traccar_trip')
        action['domain'] = [('device_id', '=', self.id)]
        return action

    @api.model
    def _handle_webhook(self, server, payload):
        """Traccar event/position forwarding: {'position': {...}, 'device': {...}, 'event': {...}} or a bare position."""
        position = payload.get('position') or (payload if 'latitude' in payload else None)
        event = payload.get('event')
        device_info = payload.get('device') if isinstance(payload.get('device'), dict) else {}
        if not isinstance(position, (dict, type(None))) or not isinstance(event, (dict, type(None))):
            return False
        device_id = device_info.get('id') or (position or {}).get('deviceId') or (event or {}).get('deviceId')
        device = self.search([('server_id', '=', server.id), ('traccar_id', '=', device_id)], limit=1)
        if not device or not device.tracking_enabled:
            return False
        if device_info.get('status'):
            device.status = device_info['status']
        if position:
            device._apply_position(position)
        if event and device.vehicle_id:
            label = event.get('type', 'event')
            alarm = (event.get('attributes') or {}).get('alarm')
            device.vehicle_id.message_post(body=_("GPS event: %(type)s%(alarm)s",
                                                  type=label, alarm=f" ({alarm})" if alarm else ''))
        return True
