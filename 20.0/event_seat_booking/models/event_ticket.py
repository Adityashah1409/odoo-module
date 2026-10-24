from odoo import api, fields, models
from odoo.exceptions import UserError


class EventEventTicket(models.Model):
    _name = 'event.event.ticket'
    _inherit = ['event.event.ticket', 'event.seat.layout.mixin']

    seat_plan_id = fields.Many2one('event.seat.plan', string='Seating plan',
                                   help='Copy the layout of a saved plan (venue template).')
    seat_surcharge_ids = fields.One2many('event.seat.surcharge', 'ticket_id', string='Premium rows', copy=True)
    seat_ids = fields.One2many('event.seat', 'ticket_id', string='Seats')
    seat_count = fields.Integer('Seats for Sale', compute='_compute_seat_stats')
    seat_available_count = fields.Integer('Free seats', compute='_compute_seat_stats')
    seat_booked_count = fields.Integer('Booked seats', compute='_compute_seat_stats')
    seat_held_count = fields.Integer('Seats on hold', compute='_compute_seat_stats')
    seat_map_preview = fields.Html('Seat map', compute='_compute_seat_map_preview', sanitize=False)

    def _seat_surcharge_lines(self):
        return self.seat_surcharge_ids

    @api.depends('seat_ids.state')
    def _compute_seat_stats(self):
        groups = self.env['event.seat']._read_group([('ticket_id', 'in', self.ids)], ['ticket_id', 'state'], ['__count'])
        stats = {}
        for ticket, state, count in groups:
            stats.setdefault(ticket.id, {})[state] = count
        for ticket in self:
            values = stats.get(ticket.id, {})
            ticket.seat_count = sum(c for s, c in values.items() if s != 'blocked')
            ticket.seat_available_count = values.get('available', 0)
            ticket.seat_booked_count = values.get('booked', 0)
            ticket.seat_held_count = values.get('held', 0)

    @api.depends('seat_ids.state', 'seat_ids.surcharge', 'seat_rows', 'seat_columns', 'seat_row_label',
                 'seat_aisle_rows', 'seat_aisle_columns', 'seat_blocked', 'seat_stage_label',
                 'seat_surcharge_ids.rows', 'seat_surcharge_ids.amount')
    def _compute_seat_map_preview(self):
        for ticket in self:
            # real seats once prepared, otherwise a draft of the layout being edited
            data = ticket._seat_map_data() if ticket.seat_ids else ticket._layout_map_data()
            ticket.seat_map_preview = data['rows'] and self.env['ir.qweb']._render(
                'event_seat_booking.seat_map_preview',
                {'section': data, 'currency': ticket.currency_id or self.env.company.currency_id})

    @api.onchange('seat_plan_id')
    def _onchange_seat_plan_id(self):
        if self.seat_plan_id:
            self.update(self.seat_plan_id._copy_layout_values())
            self.seat_surcharge_ids = [(5, 0, 0)] + [(0, 0, {'rows': s.rows, 'amount': s.amount, 'sequence': s.sequence})
                                                     for s in self.seat_plan_id.surcharge_ids]

    def action_apply_plan(self):
        for ticket in self.filtered('seat_plan_id'):
            ticket.write({**ticket.seat_plan_id._copy_layout_values(),
                          'seat_surcharge_ids': [(5, 0, 0)] + [
                              (0, 0, {'rows': s.rows, 'amount': s.amount, 'sequence': s.sequence})
                              for s in ticket.seat_plan_id.surcharge_ids]})
        return True

    def action_prepare_seats(self):
        """(Re)build the seats of the section from its layout."""
        for ticket in self:
            if ticket.event_id.is_multi_slots:
                raise UserError(self.env._('Seat maps are not available for events with time slots.'))
            if not (ticket.seat_rows and ticket.seat_columns):
                raise UserError(self.env._('Set the number of rows and seats per row first.'))
            busy = ticket.seat_ids.filtered(lambda s: s.state in ('held', 'booked') or s.registration_id)
            if busy:
                raise UserError(self.env._(
                    'Some seats of %(section)s are already sold or on hold (%(seats)s). Rebuilding is not possible; '
                    'block or edit seats one by one instead.', section=ticket.name,
                    seats=', '.join(busy[:10].mapped('name'))))
            ticket.seat_ids.unlink()
            cells = ticket._seat_cells()
            self.env['event.seat'].create([{
                'ticket_id': ticket.id, 'name': cell['name'], 'row_label': cell['row_label'],
                'row_number': cell['row_number'], 'number': cell['number'], 'row_index': cell['row_index'],
                'column_index': cell['column_index'], 'surcharge': cell['surcharge'],
                'state': 'blocked' if cell['blocked'] else 'available'} for cell in cells])
            ticket.event_id.seat_booking = True
            ticket._sync_seats_max()
        return True

    def action_clear_seats(self):
        for ticket in self:
            if ticket.seat_ids.filtered(lambda s: s.state in ('held', 'booked') or s.registration_id):
                raise UserError(self.env._('Seats of %s are sold or on hold: they cannot be removed.', ticket.name))
            ticket.seat_ids.unlink()
        return True

    def _sync_seats_max(self):
        """The ticket capacity follows the number of sellable seats."""
        for ticket in self.filtered('seat_ids'):
            ticket.seats_max = len(ticket.seat_ids.filtered(lambda s: s.state != 'blocked'))

    def action_open_seating(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'event.event.ticket', 'res_id': self.id,
            'views': [(self.env.ref('event_seat_booking.event_event_ticket_view_form_seating').id, 'form')],
            'target': 'current', 'name': self.env._('Seats - %s', self.name),
        }

    def action_view_seats(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('event_seat_booking.action_event_seat')
        action.update({'domain': [('ticket_id', '=', self.id)], 'context': {'default_ticket_id': self.id}})
        return action

    def _seat_map_data(self, token=None):
        """Rows and cells for the website and backend seat maps."""
        self.ensure_one()
        seats = self.seat_ids.sorted(lambda s: (s.row_index, s.column_index))
        width = (max(seats.mapped('column_index')) + 1) if seats else 0
        rows = {}
        for seat in seats:
            status = seat.state
            if status == 'held' and seat._is_free_for(token):
                status = 'mine' if token and seat.hold_token == token else 'available'
            rows.setdefault(seat.row_index, {'label': seat.row_label, 'index': seat.row_index, 'cells': {}})
            rows[seat.row_index]['cells'][seat.column_index] = {
                'id': seat.id, 'name': seat.name, 'number': seat.number, 'status': status,
                'surcharge': seat.surcharge, 'price': seat.price}
        height = (max(rows) + 1) if rows else 0
        grid = []
        for index in range(height):
            row = rows.get(index)
            grid.append({'label': row['label'] if row else '', 'index': index, 'gap': not row,
                         'cells': [row['cells'].get(col) if row else None for col in range(width)]})
        return {'id': self.id, 'name': self.name, 'price': self.price, 'stage': self.seat_stage_label or '',
                'width': width, 'rows': grid, 'premium': bool(seats.filtered('surcharge'))}
