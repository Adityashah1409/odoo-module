from odoo import api, fields, models


class EventSeatPlan(models.Model):
    """Reusable seating plan (venue template)."""
    _name = 'event.seat.plan'
    _description = 'Seating plan'
    _inherit = ['event.seat.layout.mixin']
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company,
                                 help='Leave empty to share the plan with every company.')
    website_id = fields.Many2one('website', help='Restrict the plan to one website.')
    surcharge_ids = fields.One2many('event.seat.surcharge', 'plan_id', string='Premium rows', copy=True)
    seat_count = fields.Integer('Seats', compute='_compute_seat_count')
    note = fields.Text()
    seat_map_preview = fields.Html('Preview', compute='_compute_seat_map_preview', sanitize=False)

    @api.depends('seat_rows', 'seat_columns', 'seat_row_label', 'seat_aisle_rows', 'seat_aisle_columns',
                 'seat_blocked', 'seat_stage_label', 'surcharge_ids.rows', 'surcharge_ids.amount')
    def _compute_seat_map_preview(self):
        for plan in self:
            data = plan._layout_map_data()
            plan.seat_map_preview = data['rows'] and self.env['ir.qweb']._render(
                'event_seat_booking.seat_map_preview', {'section': data, 'currency': self.env.company.currency_id})

    def _seat_surcharge_lines(self):
        return self.surcharge_ids

    def _compute_seat_count(self):
        for plan in self:
            plan.seat_count = len([c for c in plan._seat_cells() if not c['blocked']])
