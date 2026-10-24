from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.traccar_server import TraccarError


class TraccarTripImportWizard(models.TransientModel):
    _name = 'traccar.trip.import.wizard'
    _description = 'Import trips from Traccar'

    date_from = fields.Datetime(required=True, default=lambda self: fields.Datetime.now() - timedelta(days=7))
    date_to = fields.Datetime(required=True, default=fields.Datetime.now)
    vehicle_ids = fields.Many2many('fleet.vehicle', string="Vehicles",
                                   domain=[('traccar_device_ids', '!=', False)],
                                   help="Leave empty to import trips of every tracked vehicle.")

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from >= wizard.date_to:
                raise UserError(_("The start date must be before the end date."))

    def action_import(self):
        devices = self.vehicle_ids.traccar_device_ids if self.vehicle_ids else \
            self.env['traccar.device'].search([('vehicle_id', '!=', False)])
        trips = self.env['traccar.trip']
        for server in devices.server_id:
            try:
                trips |= server._import_trips(self.date_from, self.date_to, devices.filtered(lambda d: d.server_id == server))
            except TraccarError as e:
                raise UserError(_("Trip import failed on %(server)s:\n%(error)s", server=server.name, error=e)) from e
        action = self.env['ir.actions.act_window']._for_xml_id('fleet_traccar_tracking.action_traccar_trip')
        action['domain'] = [('device_id', 'in', devices.ids)]
        action['context'] = {}
        return action
