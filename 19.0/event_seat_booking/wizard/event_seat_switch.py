from odoo import api, fields, models
from odoo.exceptions import UserError


class EventSeatSwitch(models.TransientModel):
    _name = 'event.seat.switch'
    _description = 'Switch the seat of an attendee'

    registration_id = fields.Many2one('event.registration', required=True)
    event_id = fields.Many2one(related='registration_id.event_id')
    current_seat_id = fields.Many2one(related='registration_id.seat_id', string='Current seat')
    same_section = fields.Boolean('Same section only', default=True)
    ticket_id = fields.Many2one(related='registration_id.event_ticket_id')
    seat_id = fields.Many2one('event.seat', string='New seat', required=True,
                              domain="[('event_id', '=', event_id), ('state', '=', 'available'), "
                                     "'|', ('ticket_id', '=', ticket_id), ('ticket_id', '!=', same_section and ticket_id)]")
    price_difference = fields.Float(compute='_compute_price_difference', digits='Product Price')

    @api.depends('seat_id', 'current_seat_id')
    def _compute_price_difference(self):
        for wizard in self:
            wizard.price_difference = (wizard.seat_id.price - wizard.current_seat_id.price) if wizard.seat_id else 0.0

    def action_switch(self):
        self.ensure_one()
        if self.registration_id.state == 'cancel':
            raise UserError(self.env._('This registration is cancelled.'))
        self.registration_id.write({'seat_id': self.seat_id.id})
        self.registration_id.message_post(body=self.env._('Seat switched to %s.', self.seat_id.display_name))
        return {'type': 'ir.actions.act_window_close'}
