import json
import re

from odoo.tests import HttpCase, new_test_user, tagged

from .common import make_event


@tagged('post_install', '-at_install')
class TestWebsiteSeats(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.event = make_event(cls.env, name='Opera night')
        cls.standard = cls.event.event_ticket_ids.filtered(lambda t: t.name == 'Standard')
        cls.free_event = make_event(cls.env, name='Free rehearsal', price=0.0, vip_price=0.0)
        cls.free_event.event_ticket_ids.seat_surcharge_ids.unlink()
        cls.free_event.event_ticket_ids.seat_ids.write({'surcharge': 0.0})

    def seat(self, event, name, section='Standard'):
        return event.event_ticket_ids.filtered(lambda t: t.name == section).seat_ids.filtered(lambda s: s.name == name)

    def _json(self, url, **params):
        response = self.url_open(url, data=json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params}),
                                 headers={'Content-Type': 'application/json'})
        return response.json()['result']

    def _confirm(self, event, seats):
        page = self.url_open(f'/event/{event.id}/seats/attendees')
        self.assertEqual(page.status_code, 200)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        data = {'csrf_token': token}
        for index, seat in enumerate(seats, start=1):
            data.update({f'{index}-seat_id': seat.id, f'{index}-event_ticket_id': seat.ticket_id.id,
                         f'{index}-name': f'Guest {index}', f'{index}-email': f'guest{index}@example.com'})
        return self.url_open(f'/event/{event.id}/registration/confirm', data=data)

    def test_event_page_and_seat_map(self):
        page = self.url_open(f'/event/{self.event.id}/register')
        self.assertIn('Choose your seats', page.text)
        seats_page = self.url_open(f'/event/{self.event.id}/seats')
        self.assertEqual(seats_page.status_code, 200)
        self.assertIn('o_seat_map', seats_page.text)
        self.assertIn('data-seat-name="B2"', seats_page.text)
        best = self._json('/event/seats/best', ticket_id=self.standard.id, count=2)
        self.assertEqual(len(best['seat_ids']), 2)

    def test_paid_booking_with_premium_seat(self):
        a2, b2 = self.seat(self.event, 'A2'), self.seat(self.event, 'B2')
        result = self._json('/event/seats/hold', event_id=self.event.id, seat_ids=[a2.id, b2.id])
        self.assertEqual(sorted(result['held']), sorted([a2.id, b2.id]))
        self.assertEqual(a2.state, 'held')
        response = self._confirm(self.event, a2 | b2)
        self.assertIn('/shop/', response.url)
        registrations = self.env['event.registration'].search([('event_id', '=', self.event.id)])
        self.assertEqual(registrations.seat_id, a2 | b2)
        self.assertEqual(set(registrations.mapped('state')), {'draft'})
        order = registrations.sale_order_id
        self.assertEqual(len(order), 1)
        ticket_line = order.order_line.filtered('event_ticket_id')
        self.assertEqual((ticket_line.product_uom_qty, ticket_line.price_unit), (2, 30.0))
        surcharge = order.order_line.filtered('seat_id')
        self.assertEqual((surcharge.seat_id, surcharge.price_unit), (a2, 10.0))
        self.assertEqual(order.amount_untaxed, 70.0)
        order.action_confirm()
        self.assertEqual(set(registrations.mapped('state')), {'open'})
        self.assertEqual(set((a2 | b2).mapped('state')), {'booked'})

    def test_cancelled_cart_releases_seats(self):
        c5 = self.seat(self.event, 'C5')
        self._json('/event/seats/hold', event_id=self.event.id, seat_ids=[c5.id])
        self._confirm(self.event, c5)
        order = c5.registration_id.sale_order_id
        self.assertTrue(order)
        order._action_cancel()
        self.assertEqual(c5.registration_id.state if c5.registration_id else 'cancel', 'cancel')
        self.assertEqual(c5.state, 'available')

    def test_free_booking(self):
        c3 = self.seat(self.free_event, 'C3')
        self._json('/event/seats/hold', event_id=self.free_event.id, seat_ids=[c3.id])
        response = self._confirm(self.free_event, c3)
        self.assertIn('registration/success', response.url)
        self.assertEqual(c3.state, 'booked')
        self.assertEqual(c3.registration_id.name, 'Guest 1')

    def test_taken_or_expired(self):
        b4 = self.seat(self.event, 'B4')
        self.env['event.registration'].create({'event_id': self.event.id, 'name': 'X', 'email': 'x@x.com', 'seat_id': b4.id})
        result = self._json('/event/seats/hold', event_id=self.event.id, seat_ids=[b4.id])
        self.assertIn('just taken', result['error'])
        no_hold = self.url_open(f'/event/{self.event.id}/seats/attendees')
        self.assertIn('error=expired', no_hold.url)
        self.assertIn('no longer reserved', no_hold.text)

    def test_sold_out_waitlist(self):
        event = self.free_event
        self.env['event.registration'].create([
            {'event_id': event.id, 'name': f'Guest {seat.name}', 'email': 'g@example.com', 'seat_id': seat.id}
            for seat in event.event_ticket_ids.seat_ids.filtered(lambda s: s.state == 'available')])
        self.assertFalse(event.event_registrations_open)
        self.assertIn('Join the waitlist', self.url_open(f'/event/{event.id}/register').text)
        page = self.url_open(f'/event/{event.id}/seats')
        self.assertIn('Join the waitlist', page.text)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        self.url_open(f'/event/{event.id}/waitlist', data={'csrf_token': token, 'name': 'Wait Er', 'email': 'WAIT@example.com'})
        self.assertEqual(event.seat_waitlist_ids.email, 'wait@example.com')

    def test_portal_exchange(self):
        user = new_test_user(self.env, 'seat_portal', password='seat_portal_pw', groups='base.group_portal')
        b2 = self.seat(self.event, 'B2')
        registration = self.env['event.registration'].create({'event_id': self.event.id, 'name': 'Portal guest',
                                                              'email': 'p@example.com', 'seat_id': b2.id,
                                                              'partner_id': user.partner_id.id})
        self.env['ir.config_parameter'].sudo().set_bool('event_seat_booking.portal_exchange', True)
        self.authenticate('seat_portal', 'seat_portal_pw')
        listing = self.url_open('/my/seats')
        self.assertIn('Change seat', listing.text)
        page = self.url_open(f'/my/seats/{registration.id}/change')
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        # same price -> immediate
        c2 = self.seat(self.event, 'C2')
        response = self.url_open(f'/my/seats/{registration.id}/change', data={'csrf_token': token, 'seat_id': c2.id})
        self.assertIn('changed=1', response.url)
        self.assertEqual(registration.seat_id, c2)
        self.assertEqual(b2.state, 'available')
        # premium seat -> order for the difference
        a3 = self.seat(self.event, 'A3')
        response = self.url_open(f'/my/seats/{registration.id}/change', data={'csrf_token': token, 'seat_id': a3.id})
        order = self.env['sale.order'].search([('order_line.seat_upgrade_registration_id', '=', registration.id)])
        self.assertEqual(order.amount_untaxed, 10.0)
        self.assertIn(f'/my/orders/{order.id}', response.url)
        self.assertEqual(a3.state, 'held')
        order.action_confirm()
        self.assertEqual(registration.seat_id, a3)

    def test_tour(self):
        self.start_tour(f'/event/{self.free_event.id}/seats', 'event_seat_booking_tour')
        registrations = self.env['event.registration'].search([('event_id', '=', self.free_event.id)])
        self.assertEqual(len(registrations), 2)
        self.assertEqual(set(registrations.seat_id.mapped('state')), {'booked'})
