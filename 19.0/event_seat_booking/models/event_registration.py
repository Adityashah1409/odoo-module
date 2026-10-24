from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class EventRegistration(models.Model):
    _inherit = 'event.registration'

    seat_id = fields.Many2one('event.seat', string='Seat', index='btree_not_null', copy=False, tracking=True,
                              domain="[('event_id', '=', event_id), ('state', '=', 'available')]")
    seat_name = fields.Char(related='seat_id.name', string='Seat number')
    seat_section = fields.Char(related='seat_id.ticket_id.name', string='Section')
    seat_released_id = fields.Many2one('event.seat', string='Released seat', readonly=True, copy=False,
                                       help='Seat that was held for this attendee and released before payment.')

    def _get_website_registration_allowed_fields(self):
        return super()._get_website_registration_allowed_fields() | {'seat_id'}

    @api.constrains('seat_id', 'state', 'event_id', 'event_ticket_id')
    def _check_seat(self):
        for registration in self.filtered(lambda r: r.seat_id and r.state != 'cancel'):
            seat = registration.seat_id
            if seat.event_id != registration.event_id:
                raise ValidationError(self.env._('Seat %s does not belong to this event.', seat.name))
            if registration.event_ticket_id and seat.ticket_id != registration.event_ticket_id:
                raise ValidationError(self.env._('Seat %(seat)s is in section %(section)s, not %(ticket)s.',
                                                 seat=seat.name, section=seat.ticket_id.name,
                                                 ticket=registration.event_ticket_id.name))
            if self.search_count([('seat_id', '=', seat.id), ('state', '!=', 'cancel'),
                                  ('id', '!=', registration.id)], limit=1):
                raise ValidationError(self.env._('Seat %s is already taken.', seat.name))

    def _check_seat_free(self, seat):
        token = self.env.context.get('seat_hold_token')
        if seat.state == 'blocked':
            raise UserError(self.env._('Seat %s is not for sale.', seat.name))
        if not seat._is_free_for(token) and seat.registration_id not in self:
            raise UserError(self.env._('Seat %s is already taken.', seat.name))

    @api.model_create_multi
    def create(self, vals_list):
        Seat = self.env['event.seat']
        for vals in vals_list:
            if vals.get('seat_id'):
                seat = Seat.browse(vals['seat_id'])
                seat._lock()
                self._check_seat_free(seat)
                vals.setdefault('event_ticket_id', seat.ticket_id.id)
                vals.setdefault('event_id', seat.event_id.id)
        registrations = super().create(vals_list)
        for registration in registrations.filtered('seat_id'):
            registration.seat_id._assign(registration)
        return registrations

    def write(self, vals):
        new_seat = self.env['event.seat'].browse(vals['seat_id']) if vals.get('seat_id') else None
        old_seats = {r.id: r.seat_id for r in self} if 'seat_id' in vals else {}
        if new_seat:
            if len(self) > 1:
                raise UserError(self.env._('One seat cannot be given to several attendees.'))
            new_seat._lock()
            self._check_seat_free(new_seat)
            if self.event_ticket_id and new_seat.ticket_id != self.event_ticket_id and 'event_ticket_id' not in vals:
                vals['event_ticket_id'] = new_seat.ticket_id.id
        res = super().write(vals)
        if 'seat_id' in vals:
            for registration in self:
                old = old_seats.get(registration.id)
                if old and old != registration.seat_id and old.registration_id == registration:
                    old._release()
                if registration.seat_id and registration.state != 'cancel':
                    registration.seat_id._assign(registration)
        if 'state' in vals:
            self._seat_follow_state()
        return res

    def _seat_follow_state(self):
        for registration in self:
            seat = registration.seat_id
            if registration.state == 'cancel':
                if seat and seat.registration_id == registration:
                    line = seat.sale_line_id
                    if line and line.order_id.state in ('draft', 'sent'):
                        line.sudo().unlink()
                    seat._release()
            elif registration.state in ('open', 'done'):
                if seat and seat.registration_id in (registration, self.env['event.registration']) and \
                        seat.state != 'blocked':
                    seat._assign(registration)
                elif seat and seat.registration_id and seat.registration_id != registration:
                    registration._seat_conflict(seat)
                elif not seat and registration.seat_released_id:
                    released = registration.seat_released_id
                    if released._is_free_for(None):
                        registration.with_context(seat_hold_token=False).write(
                            {'seat_id': released.id, 'seat_released_id': False})
                    else:
                        registration._seat_conflict(released)

    def _seat_conflict(self, seat):
        """Paid after the hold expired and the seat went to someone else: ask the organizer to pick another one."""
        self.ensure_one()
        super(EventRegistration, self).write({'seat_id': False, 'seat_released_id': seat.id})
        self.message_post(body=Markup('<p>%s</p>') % self.env._(
            'Seat %s was given to someone else before this registration was paid. Choose another seat with '
            '"Switch seat".', seat.name))
        self.activity_schedule('mail.mail_activity_data_todo', summary=self.env._('Assign a seat'),
                               user_id=self.event_id.user_id.id or self.env.user.id)

    def action_switch_seat(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'event.seat.switch', 'view_mode': 'form',
            'views': [(False, 'form')], 'target': 'new', 'name': self.env._('Switch seat'),
            'context': {'default_registration_id': self.id},
        }
