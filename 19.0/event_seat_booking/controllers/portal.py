from odoo import fields, http
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

from .main import PARAM, _session_token


class EventSeatPortal(CustomerPortal):

    def _seat_registrations(self):
        partner = request.env.user.partner_id
        return request.env['event.registration'].sudo().search([
            ('partner_id', 'child_of', partner.commercial_partner_id.id), ('seat_id', '!=', False),
            ('state', 'in', ('draft', 'open', 'done'))]).sorted(lambda r: (r.event_id.date_begin, r.id), reverse=True)

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'event_seat_count' in counters:
            values['event_seat_count'] = len(self._seat_registrations())
        return values

    @staticmethod
    def _exchange_enabled():
        return bool(request.env['ir.config_parameter'].sudo().get_param(PARAM + 'portal_exchange'))

    def _own_registration(self, registration_id):
        registration = request.env['event.registration'].sudo().browse(registration_id).exists()
        if not registration or registration not in self._seat_registrations():
            return None
        return registration

    @http.route(['/my/seats'], type='http', auth='user', website=True)
    def portal_my_seats(self, **kwargs):
        values = self._prepare_portal_layout_values()
        values.update({'registrations': self._seat_registrations(), 'page_name': 'event_seats',
                       'exchange': self._exchange_enabled(), 'changed': kwargs.get('changed')})
        return request.render('event_seat_booking.portal_my_seats', values)

    @http.route(['/my/seats/<int:registration_id>/change'], type='http', auth='user', website=True,
                methods=['GET', 'POST'])
    def portal_change_seat(self, registration_id, seat_id=None, **kwargs):
        registration = self._own_registration(registration_id)
        if not registration or not self._exchange_enabled() or registration.state not in ('open', 'draft') or \
                registration.event_id.date_begin <= fields.Datetime.now():
            return request.redirect('/my/seats')
        event = registration.event_id
        token = _session_token()
        error = None
        if request.httprequest.method == 'POST' and seat_id:
            seat = request.env['event.seat'].sudo().browse(int(seat_id)).exists()
            try:
                if not seat or seat.event_id != event or seat.ticket_id != registration.event_ticket_id:
                    raise UserError(request.env._('Choose a seat in your section (%s).',
                                                  registration.event_ticket_id.name))
                difference = seat.price - registration.seat_id.price
                seat._hold(token)
                if difference <= 0:
                    registration.with_context(seat_hold_token=token).write({'seat_id': seat.id})
                    registration.message_post(body=request.env._('Seat changed to %s from the portal.', seat.name))
                    return request.redirect('/my/seats?changed=1')
                order = self._seat_upgrade_order(registration, seat, difference)
                seat.hold_token = f'upgrade-{order.id}'
                seat.hold_until = fields.Datetime.add(fields.Datetime.now(), days=2)
                return request.redirect(order.get_portal_url())
            except UserError as exc:
                error = str(exc)
        values = self._prepare_portal_layout_values()
        values.update({
            'registration': registration, 'event': event, 'page_name': 'event_seats_change', 'error': error,
            'section': self._seat_section_with_current(registration, token),
            'currency': event.currency_id or request.website.currency_id,
        })
        return request.render('event_seat_booking.portal_change_seat', values)

    @staticmethod
    def _seat_section_with_current(registration, token):
        section = registration.event_ticket_id._seat_map_data(token)
        for row in section['rows']:
            for cell in row['cells']:
                if cell and cell['id'] == registration.seat_id.id:
                    cell['status'] = 'current'
        return section

    def _seat_upgrade_order(self, registration, seat, difference):
        product = request.env['event.seat']._surcharge_product()
        partner = request.env.user.partner_id
        return request.env['sale.order'].sudo().create({
            'partner_id': partner.id, 'website_id': request.website.id, 'company_id': registration.event_id.company_id.id
            or request.website.company_id.id,
            'order_line': [(0, 0, {
                'product_id': product.id, 'product_uom_qty': 1, 'price_unit': difference,
                'name': request.env._('Seat change %(old)s → %(new)s - %(event)s', old=registration.seat_id.name,
                                      new=seat.name, event=registration.event_id.name),
                'seat_upgrade_registration_id': registration.id, 'seat_upgrade_seat_id': seat.id})],
        })
