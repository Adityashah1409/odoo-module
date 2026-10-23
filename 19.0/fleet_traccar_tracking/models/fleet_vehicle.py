from odoo import _, api, fields, models
from odoo.exceptions import UserError


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    traccar_device_ids = fields.One2many('traccar.device', 'vehicle_id')
    traccar_device_id = fields.Many2one('traccar.device', string="GPS device", compute='_compute_traccar_device',
                                        inverse='_inverse_traccar_device', search='_search_traccar_device')
    gps_latitude = fields.Float("Latitude", digits=(10, 7), readonly=True)
    gps_longitude = fields.Float("Longitude", digits=(10, 7), readonly=True)
    gps_speed = fields.Float("Speed (km/h)", digits=(6, 1), readonly=True)
    gps_fix_time = fields.Datetime("Last position", readonly=True)
    gps_accuracy = fields.Float("Accuracy (m)", readonly=True)
    gps_battery_level = fields.Float("Device battery (%)", readonly=True)
    gps_address = fields.Char("GPS address", readonly=True)
    gps_motion_state = fields.Selection([('moving', 'Moving'), ('stopped', 'Stopped'), ('offline', 'Offline')],
                                        string="GPS status", readonly=True)
    gps_map_html = fields.Html("Map", compute='_compute_gps_map_html', sanitize=False)
    trip_count = fields.Integer(compute='_compute_trip_count')

    @api.depends('traccar_device_ids')
    def _compute_traccar_device(self):
        for vehicle in self:
            vehicle.traccar_device_id = vehicle.traccar_device_ids[:1]

    def _inverse_traccar_device(self):
        for vehicle in self:
            (vehicle.traccar_device_ids - vehicle.traccar_device_id).vehicle_id = False
            if vehicle.traccar_device_id:
                vehicle.traccar_device_id.vehicle_id = vehicle

    def _search_traccar_device(self, operator, value):
        return [('traccar_device_ids', operator, value)]

    @api.depends('gps_latitude', 'gps_longitude')
    def _compute_gps_map_html(self):
        for vehicle in self:
            if not (vehicle.gps_latitude or vehicle.gps_longitude):
                vehicle.gps_map_html = False
                continue
            lat, lon, d = vehicle.gps_latitude, vehicle.gps_longitude, 0.01
            vehicle.gps_map_html = (
                '<iframe style="width:100%;height:320px;border:0;border-radius:8px" loading="lazy" '
                f'src="https://www.openstreetmap.org/export/embed.html?bbox={lon - d},{lat - d},{lon + d},{lat + d}'
                f'&amp;layer=mapnik&amp;marker={lat},{lon}"></iframe>')

    def _compute_trip_count(self):
        counts = dict(self.env['traccar.trip']._read_group([('vehicle_id', 'in', self.ids)], ['vehicle_id'], ['__count']))
        for vehicle in self:
            vehicle.trip_count = counts.get(vehicle, 0)

    def _gps_update_odometer(self, total_km, date):
        """Log an odometer reading when the GPS total distance went up by at least 1 km."""
        self.ensure_one()
        self.invalidate_recordset(['odometer'])  # fleet computes it without dependencies
        if total_km >= (self.odometer or 0.0) + 1:
            self.env['fleet.vehicle.odometer'].create({
                'vehicle_id': self.id, 'value': round(total_km, 1),
                'date': fields.Date.to_date(date) if date else fields.Date.today(),
            })
            self.invalidate_recordset(['odometer'])

    def action_open_gps_map(self):
        self.ensure_one()
        if not (self.gps_latitude or self.gps_longitude):
            raise UserError(_("No GPS position yet for %s.", self.display_name))
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': f"https://www.openstreetmap.org/?mlat={self.gps_latitude}&mlon={self.gps_longitude}"
                       f"#map=16/{self.gps_latitude}/{self.gps_longitude}"}

    def action_view_trips(self):
        action = self.env['ir.actions.act_window']._for_xml_id('fleet_traccar_tracking.action_traccar_trip')
        action['domain'] = [('vehicle_id', 'in', self.ids)]
        action['context'] = {'default_vehicle_id': self.id}
        return action

    def action_import_trips(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': 'traccar.trip.import.wizard', 'view_mode': 'form',
            'target': 'new', 'context': {'default_vehicle_ids': self.ids},
        }

    def action_live_map(self):
        ids = ','.join(str(i) for i in self.ids)
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': f'/fleet_traccar_tracking/map?vehicle_ids={ids}' if ids else '/fleet_traccar_tracking/map'}
