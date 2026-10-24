from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    seat_hold_minutes = fields.Integer('Seat hold (minutes)', config_parameter='event_seat_booking.hold_minutes',
                                       default=15,
                                       help='How long seats chosen on the website stay reserved before payment.')
    seat_auto_allocate = fields.Boolean('Best available seats', config_parameter='event_seat_booking.auto_allocate',
                                        help='"Find the best seats" button on the seat map.')
    seat_portal_exchange = fields.Boolean('Seat change from the portal',
                                          config_parameter='event_seat_booking.portal_exchange',
                                          help='Attendees can change their seat from My Account; a more expensive '
                                               'seat creates a quotation to pay the difference.')
    seat_surcharge_product_id = fields.Many2one(
        'product.product', string='Seat surcharge product', config_parameter='event_seat_booking.surcharge_product_id',
        default=lambda self: (self.env.ref('event_seat_booking.product_seat_surcharge', raise_if_not_found=False)
                              or self.env['product.product']).id,
        help='Product used for premium seat surcharges and seat upgrades in orders.')
