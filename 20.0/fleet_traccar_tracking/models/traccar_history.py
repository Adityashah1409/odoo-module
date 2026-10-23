from odoo import api, fields, models


class TraccarPosition(models.Model):
    _name = 'traccar.position'
    _description = 'GPS Position'
    _order = 'fix_time desc, id desc'
    _rec_name = 'fix_time'

    device_id = fields.Many2one('traccar.device', required=True, ondelete='cascade', index=True)
    vehicle_id = fields.Many2one('fleet.vehicle', ondelete='set null', index=True)
    traccar_id = fields.Integer("Traccar ID")
    fix_time = fields.Datetime(required=True, index=True)
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))
    speed = fields.Float("Speed (km/h)", digits=(6, 1))
    course = fields.Float()
    altitude = fields.Float()
    accuracy = fields.Float("Accuracy (m)")
    battery_level = fields.Float("Battery (%)")
    address = fields.Char()
    moving = fields.Boolean()
    attributes = fields.Text()
    map_url = fields.Char(compute='_compute_map_url')

    @api.depends('latitude', 'longitude')
    def _compute_map_url(self):
        for position in self:
            position.map_url = (f"https://www.openstreetmap.org/?mlat={position.latitude}&mlon={position.longitude}"
                                f"#map=16/{position.latitude}/{position.longitude}")


class TraccarTrip(models.Model):
    _name = 'traccar.trip'
    _description = 'Vehicle Trip'
    _order = 'start_time desc, id desc'
    _rec_name = 'start_time'

    device_id = fields.Many2one('traccar.device', required=True, ondelete='cascade', index=True)
    vehicle_id = fields.Many2one('fleet.vehicle', ondelete='cascade', index=True)
    driver_name = fields.Char()
    start_time = fields.Datetime(required=True)
    end_time = fields.Datetime()
    duration = fields.Float("Duration (h)", compute='_compute_duration', store=True)
    start_address = fields.Char()
    end_address = fields.Char()
    start_latitude = fields.Float(digits=(10, 7))
    start_longitude = fields.Float(digits=(10, 7))
    end_latitude = fields.Float(digits=(10, 7))
    end_longitude = fields.Float(digits=(10, 7))
    distance_km = fields.Float("Distance (km)", digits=(10, 2))
    average_speed = fields.Float("Avg speed (km/h)", digits=(6, 1))
    max_speed = fields.Float("Max speed (km/h)", digits=(6, 1))

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for trip in self:
            trip.duration = ((trip.end_time - trip.start_time).total_seconds() / 3600.0
                             if trip.start_time and trip.end_time else 0.0)

    def action_open_route(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': ("https://www.openstreetmap.org/directions?route="
                        f"{self.start_latitude},{self.start_longitude};{self.end_latitude},{self.end_longitude}")}
