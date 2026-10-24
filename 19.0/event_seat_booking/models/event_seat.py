from datetime import timedelta

from psycopg2 import errors as pg_errors

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import mute_logger

PARAM = 'event_seat_booking.'
DEFAULT_HOLD_MINUTES = 15


class EventSeat(models.Model):
    _name = 'event.seat'
    _description = 'Event seat'
    _order = 'ticket_id, row_index, column_index, id'

    name = fields.Char(required=True)
    ticket_id = fields.Many2one('event.event.ticket', string='Section', required=True, ondelete='cascade', index=True)
    event_id = fields.Many2one(related='ticket_id.event_id', store=True, index=True)
    company_id = fields.Many2one(related='event_id.company_id', store=True)
    row_label = fields.Char('Row')
    row_number = fields.Integer(aggregator=None)
    number = fields.Integer('Seat', aggregator=None)
    row_index = fields.Integer('Display row', aggregator=None)
    column_index = fields.Integer('Display column', aggregator=None)
    surcharge = fields.Float(digits='Product Price', help='Added to the ticket price for this seat.')
    price = fields.Float(compute='_compute_price', digits='Product Price')
    state = fields.Selection([('available', 'Available'), ('held', 'On hold'), ('booked', 'Booked'),
                              ('blocked', 'Blocked')], default='available', required=True, index=True)
    registration_id = fields.Many2one('event.registration', string='Attendee', index='btree_not_null',
                                      ondelete='set null', readonly=True)
    attendee_name = fields.Char(related='registration_id.name', string='Attendee name')
    hold_token = fields.Char(readonly=True, copy=False)
    hold_until = fields.Datetime(readonly=True, copy=False)
    sale_line_id = fields.Many2one('sale.order.line', string='Surcharge line', readonly=True, copy=False,
                                   ondelete='set null')

    _ticket_name_uniq = models.Constraint('UNIQUE(ticket_id, name)', 'Seat names must be unique in a section.')

    @api.depends('surcharge', 'ticket_id.price')
    def _compute_price(self):
        for seat in self:
            seat.price = (seat.ticket_id.price or 0.0) + seat.surcharge

    @api.depends('name', 'ticket_id.name')
    def _compute_display_name(self):
        for seat in self:
            seat.display_name = f'{seat.ticket_id.name} {seat.name}' if seat.ticket_id else seat.name

    # ------------------------------------------------------------------ helpers
    @api.model
    def _hold_minutes(self):
        return int(self.env['ir.config_parameter'].sudo().get_param(PARAM + 'hold_minutes') or DEFAULT_HOLD_MINUTES)

    def _lock(self):
        """Row-lock the seats so two buyers cannot hold the same seat at the same time."""
        if not self.ids:
            return
        try:
            with mute_logger('odoo.sql_db'), self.env.cr.savepoint():
                self.env.cr.execute('SELECT id FROM event_seat WHERE id IN %s FOR UPDATE NOWAIT', [tuple(self.ids)])
        except pg_errors.LockNotAvailable as error:
            raise UserError(self.env._('Someone is booking these seats right now. Please try again.')) from error
        self.invalidate_recordset(['state', 'hold_token', 'hold_until', 'registration_id'])

    def _is_free_for(self, token=None):
        """Can this seat be taken by the holder of ``token``?"""
        self.ensure_one()
        now = fields.Datetime.now()
        if self.state == 'available':
            return True
        if self.state == 'held' and not self.registration_id:
            return (token and self.hold_token == token) or (self.hold_until and self.hold_until < now)
        return False

    def _hold(self, token, minutes=None):
        """Hold the seats for ``token`` (a browser session); release the token's other holds in these sections."""
        if not token:
            raise UserError(self.env._('Missing booking session.'))
        self._lock()
        taken = self.filtered(lambda s: not s._is_free_for(token))
        if taken:
            raise UserError(self.env._('Sorry, these seats were just taken: %s.', ', '.join(taken.mapped('name'))))
        others = self.search([('ticket_id.event_id', 'in', self.event_id.ids), ('hold_token', '=', token),
                              ('state', '=', 'held'), ('registration_id', '=', False), ('id', 'not in', self.ids)])
        others._release()
        until = fields.Datetime.now() + timedelta(minutes=minutes or self._hold_minutes())
        self.write({'state': 'held', 'hold_token': token, 'hold_until': until})
        return until

    def _release(self):
        """Seats become available again (and waiting people are told)."""
        if not self:
            return
        events = self.event_id
        self.write({'state': 'available', 'hold_token': False, 'hold_until': False, 'registration_id': False})
        for event in events:
            freed = len(self.filtered(lambda s: s.event_id == event))
            event._seat_waitlist_notify(freed)

    def _assign(self, registration):
        """Link the seat to a registration: booked when confirmed, held while waiting for payment."""
        self.ensure_one()
        if registration.state in ('open', 'done'):
            self.write({'state': 'booked', 'registration_id': registration.id, 'hold_token': False, 'hold_until': False})
        else:
            self.write({'state': 'held', 'registration_id': registration.id,
                        'hold_until': fields.Datetime.now() + timedelta(minutes=self._hold_minutes() * 2)})

    def action_block(self):
        busy = self.filtered(lambda s: s.state in ('held', 'booked'))
        if busy:
            raise UserError(self.env._('These seats are taken: %s.', ', '.join(busy.mapped('name'))))
        self.write({'state': 'blocked'})
        self.ticket_id._sync_seats_max()
        return True

    def action_unblock(self):
        self.filtered(lambda s: s.state == 'blocked').write({'state': 'available'})
        self.ticket_id._sync_seats_max()
        return True

    def action_release(self):
        """Backend: free seats held by a website visitor (not linked to an attendee)."""
        self.filtered(lambda s: s.state == 'held' and not s.registration_id)._release()
        return True

    @api.model
    def _cron_release_expired_holds(self):
        """Seats held too long without payment become available again."""
        expired = self.search([('state', '=', 'held'), ('hold_until', '<', fields.Datetime.now())])
        for seat in expired:
            registration = seat.registration_id
            if registration and registration.state == 'draft':
                registration.write({'seat_id': False, 'seat_released_id': seat.id})
                registration.message_post(body=self.env._(
                    'Seat %s released: the order was not paid in time.', seat.name))
        expired._release()

    # ------------------------------------------------------------------ best seats
    def _best_block(self, count):
        """``count`` free seats of these (one section): together in a row, front rows first, near the centre."""
        if count <= 0 or not self:
            return self.browse()
        free = self.filtered(lambda s: s._is_free_for(None))
        if not free:
            return self.browse()
        center = (max(self.mapped('column_index')) + min(self.mapped('column_index'))) / 2
        best, best_score = None, None
        by_row = {}
        for seat in free.sorted(lambda s: (s.row_index, s.column_index)):
            by_row.setdefault(seat.row_index, []).append(seat)
        for row_index, seats in by_row.items():
            for start in range(0, len(seats) - count + 1):
                block = seats[start:start + count]
                # consecutive seat numbers; side by side is better than split by an aisle
                if any(block[i + 1].number - block[i].number != 1 for i in range(count - 1)):
                    continue
                split = block[-1].column_index - block[0].column_index != count - 1
                middle = (block[0].column_index + block[-1].column_index) / 2
                score = (split, row_index, abs(middle - center))
                if best_score is None or score < best_score:
                    best, best_score = block, score
        if best:
            return self.browse([s.id for s in best])
        # no block: the closest single seats
        ranked = free.sorted(lambda s: (s.row_index, abs(s.column_index - center)))
        return ranked[:count] if len(ranked) >= count else self.browse()

    @api.model
    def _surcharge_product(self):
        ICP = self.env['ir.config_parameter'].sudo()
        product = self.env['product.product'].sudo().browse(int(ICP.get_param(PARAM + 'surcharge_product_id') or 0)).exists()
        return product or self.env.ref('event_seat_booking.product_seat_surcharge').sudo()
