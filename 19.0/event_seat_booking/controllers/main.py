import uuid
from collections import defaultdict

from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import email_normalize

from odoo.addons.website_event_sale.controllers.main import WebsiteEventSaleController

PARAM = 'event_seat_booking.'


def _session_token():
    token = request.session.get('event_seat_hold_token')
    if not token:
        token = uuid.uuid4().hex
        request.session['event_seat_hold_token'] = token
    return token


class EventSeatController(WebsiteEventSaleController):

    # ------------------------------------------------------------------ seat map
    def _seat_sections(self, event, token):
        tickets = event.event_ticket_ids.sudo().sorted(lambda t: (t.sequence, -t.price, t.id))
        return [ticket._seat_map_data(token) for ticket in tickets
                if ticket.seat_ids and ticket.is_launched and not ticket.is_expired]

    @http.route(['/event/<model("event.event"):event>/seats'], type='http', auth='public', website=True,
                sitemap=False)
    def event_seats(self, event, **kwargs):
        sold_out = event.seat_booking and event.sudo()._seat_sold_out()
        if not event.seat_booking or (not event.event_registrations_open and not sold_out):
            return request.redirect(f'/event/{event.id}/register')
        token = _session_token()
        ICP = request.env['ir.config_parameter'].sudo()
        values = {
            'event': event, 'sections': self._seat_sections(event, token),
            'auto_allocate': bool(ICP.get_param(PARAM + 'auto_allocate')),
            'hold_minutes': request.env['event.seat'].sudo()._hold_minutes(),
            'currency': event.currency_id or request.website.currency_id,
            'sold_out': sold_out, 'error': kwargs.get('error'),
            'waitlisted': kwargs.get('waitlisted'), 'main_object': event,
        }
        return request.render('event_seat_booking.event_seat_page', values)

    @http.route(['/event/seats/hold'], type='jsonrpc', auth='public', website=True)
    def event_seats_hold(self, event_id, seat_ids, **kwargs):
        event = request.env['event.event'].browse(int(event_id)).exists()
        if not event or not event.seat_booking:
            return {'error': request.env._('This event has no seat booking.')}
        seats = request.env['event.seat'].sudo().browse([int(i) for i in seat_ids or []]).exists()
        if not seats or seats.event_id != event.sudo():
            return {'error': request.env._('Choose at least one seat.')}
        for ticket in seats.ticket_id:
            count = len(seats.filtered(lambda s: s.ticket_id == ticket))
            if ticket.limit_max_per_order and count > ticket.limit_max_per_order:
                return {'error': request.env._('At most %(count)s seats per order for %(ticket)s.',
                                               count=ticket.limit_max_per_order, ticket=ticket.name)}
            if not ticket.sale_available:
                return {'error': request.env._('%s tickets are not on sale.', ticket.name)}
        try:
            until = seats._hold(_session_token())
        except UserError as error:
            return {'error': str(error)}
        return {'held': seats.ids, 'hold_until': fields.Datetime.to_string(until),
                'next': f'/event/{event.id}/seats/attendees'}

    @http.route(['/event/seats/best'], type='jsonrpc', auth='public', website=True)
    def event_seats_best(self, ticket_id, count, **kwargs):
        ticket = request.env['event.event.ticket'].sudo().browse(int(ticket_id)).exists()
        if not ticket or not ticket.event_id.seat_booking:
            return {'seat_ids': []}
        return {'seat_ids': ticket.seat_ids._best_block(max(int(count or 1), 1)).ids}

    @http.route(['/event/<model("event.event"):event>/seats/attendees'], type='http', auth='public', website=True,
                sitemap=False)
    def event_seats_attendees(self, event, **kwargs):
        token = request.session.get('event_seat_hold_token')
        seats = request.env['event.seat'].sudo().search([
            ('event_id', '=', event.id), ('hold_token', '=', token), ('state', '=', 'held'),
            ('registration_id', '=', False), ('hold_until', '>', fields.Datetime.now())]) if token else None
        if not seats:
            return request.redirect(f'/event/{event.id}/seats?error=expired')
        partner = request.env.user.partner_id if not request.env.user._is_public() else None
        return request.render('event_seat_booking.event_seat_attendees', {
            'event': event, 'seats': seats, 'partner': partner, 'main_object': event,
            'hold_until': fields.Datetime.to_string(min(seats.mapped('hold_until'))),
            'currency': event.currency_id or request.website.currency_id,
            'total': sum(seats.mapped('price')),
        })

    @http.route(['/event/<model("event.event"):event>/waitlist'], type='http', auth='public', website=True,
                methods=['POST'], sitemap=False)
    def event_seats_waitlist(self, event, name='', email='', phone='', seats_wanted=1, **kwargs):
        email = email_normalize(email or '')
        if event.seat_booking and name.strip() and email:
            Waitlist = request.env['event.seat.waitlist'].sudo()
            if not Waitlist.search_count([('event_id', '=', event.id), ('email', '=', email)]):
                Waitlist.create({'event_id': event.id, 'name': name.strip(), 'email': email, 'phone': phone,
                                 'seats_wanted': max(int(seats_wanted or 1), 1)})
        return request.redirect(f'/event/{event.id}/seats?waitlisted=1')

    # ------------------------------------------------------------------ standard registration hooks
    def _create_attendees_from_registration_post(self, event, registration_data):
        seat_ids = [data['seat_id'] for data in registration_data if data.get('seat_id')]
        if not seat_ids:
            return super()._create_attendees_from_registration_post(event, registration_data)
        token = request.session.get('event_seat_hold_token')
        seats = request.env['event.seat'].sudo().browse(seat_ids)
        if len(set(seat_ids)) != len(seat_ids) or seats.event_id != event.sudo() or \
                seats.filtered(lambda s: not s._is_free_for(token)):
            raise UserError(request.env._('Your seats are no longer reserved. Please choose them again.'))
        for data in registration_data:
            if data.get('seat_id'):
                data['event_ticket_id'] = request.env['event.seat'].sudo().browse(data['seat_id']).ticket_id.id
        surcharged = seats.filtered('surcharge')
        if surcharged and not request.cart.id:
            request.website._create_cart()  # a premium seat is never free: go through the cart
        request.update_context(seat_hold_token=token)
        registrations = super()._create_attendees_from_registration_post(event, registration_data)
        self._add_seat_surcharges(registrations.filtered(lambda r: r.seat_id.surcharge and r.sale_order_id))
        return registrations

    def _add_seat_surcharges(self, registrations):
        product = request.env['event.seat']._surcharge_product()
        lines = defaultdict(list)
        for registration in registrations:
            lines[registration.sale_order_id].append(registration)
        for order, attendees in lines.items():
            for registration in attendees:
                seat = registration.seat_id
                line = request.env['sale.order.line'].sudo().create({
                    'order_id': order.id, 'product_id': product.id, 'product_uom_qty': 1,
                    'price_unit': seat.surcharge, 'seat_id': seat.id, 'sequence': 9999,
                    'name': request.env._('Premium seat %(seat)s - %(event)s', seat=seat.display_name,
                                          event=registration.event_id.name),
                })
                seat.sudo().sale_line_id = line

    @http.route()
    def registration_confirm(self, event, **post):
        try:
            return super().registration_confirm(event, **post)
        except UserError:
            if any(key.endswith('-seat_id') for key in post):
                return request.redirect(f'/event/{event.id}/seats?error=expired')
            raise
