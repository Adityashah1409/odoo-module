from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from .common import SeatCommon


@tagged('post_install', '-at_install')
class TestBooking(SeatCommon):

    def test_holds(self):
        b1, b2, b3 = self.seat('B1'), self.seat('B2'), self.seat('B3')
        until = (b1 | b2)._hold('token-1')
        self.assertEqual((b1.state, b1.hold_token), ('held', 'token-1'))
        self.assertTrue(until > fields.Datetime.now())
        with self.assertRaises(UserError):
            b1._hold('token-2')
        b3._hold('token-1')   # the same visitor changes their mind
        self.assertEqual((b1.state, b2.state, b3.state), ('available', 'available', 'held'))
        b3.hold_until = fields.Datetime.now() - timedelta(minutes=1)
        b3._hold('token-2')   # an expired hold can be taken
        self.assertEqual(b3.hold_token, 'token-2')
        with self.assertRaises(UserError):
            self.seat('A1')._hold('token-3')   # blocked
        with self.assertRaises(UserError):
            b1._hold(False)

    def test_registration_lifecycle(self):
        b2 = self.seat('B2')
        registration = self.register(b2)
        self.assertEqual((b2.state, b2.registration_id), ('booked', registration))
        self.assertEqual(registration.seat_name, 'B2')
        self.assertEqual(registration.event_ticket_id, self.standard, 'section taken from the seat')
        with self.assertRaises(UserError):
            self.register(b2, email='other@example.com')
        with self.assertRaises(ValidationError):
            self.register(self.seat('A2', self.vip), event_ticket_id=self.standard.id)
        waiting = self.env['event.seat.waitlist'].create({'event_id': self.event.id, 'name': 'Wanda', 'email': 'W@x.com'})
        self.assertEqual(waiting.email, 'w@x.com')
        registration.action_cancel()
        self.assertEqual((b2.state, b2.registration_id.id), ('available', False))
        self.assertEqual(waiting.state, 'notified', 'released seats are announced to the waitlist')
        mail = self.env['mail.mail'].search([('email_to', '=', 'w@x.com')])
        self.assertIn('Seats are available', mail.subject)
        # another attendee can now take it
        self.assertEqual(self.register(b2, email='new@example.com').seat_id, b2)

    def test_unpaid_hold_release_and_reassign(self):
        c1 = self.seat('C1')
        draft = self.register(c1, state='draft')
        self.assertEqual(c1.state, 'held')
        c1.hold_until = fields.Datetime.now() - timedelta(minutes=1)
        self.env['event.seat']._cron_release_expired_holds()
        self.assertEqual(c1.state, 'available')
        self.assertFalse(draft.seat_id)
        self.assertEqual(draft.seat_released_id, c1)
        # paid later, seat still free -> it gets it back
        draft.action_confirm()
        self.assertEqual((draft.seat_id, c1.state), (c1, 'booked'))
        # paid later, seat taken meanwhile -> conflict, organizer is asked
        c2 = self.seat('C2')
        late = self.register(c2, state='draft', email='late@example.com')
        c2.hold_until = fields.Datetime.now() - timedelta(minutes=1)
        self.env['event.seat']._cron_release_expired_holds()
        self.register(c2, email='fast@example.com')
        late.action_confirm()
        self.assertFalse(late.seat_id)
        self.assertTrue(late.activity_ids, 'an activity asks to assign a seat')

    def test_switch_wizard(self):
        registration = self.register(self.seat('B2'))
        wizard = Form(self.env['event.seat.switch'].with_context(default_registration_id=registration.id))
        wizard.seat_id = self.seat('A3')
        wizard = wizard.save()
        self.assertEqual(wizard.price_difference, 10.0)
        wizard.action_switch()
        self.assertEqual(registration.seat_id, self.seat('A3'))
        self.assertEqual(self.seat('B2').state, 'available')
        self.assertEqual(self.seat('A3').state, 'booked')

    def test_seat_upgrade_order(self):
        registration = self.register(self.seat('B2'), partner_id=self.env['res.partner'].create({'name': 'Seat buyer', 'email': 'buyer@example.com'}).id)
        new_seat = self.seat('A4')
        new_seat._hold('upgrade-x')
        product = self.env['event.seat']._surcharge_product()
        order = self.env['sale.order'].create({'partner_id': registration.partner_id.id, 'order_line': [(0, 0, {
            'product_id': product.id, 'price_unit': 10.0, 'seat_upgrade_registration_id': registration.id,
            'seat_upgrade_seat_id': new_seat.id})]})
        order.action_confirm()
        self.assertEqual(registration.seat_id, new_seat)
        self.assertEqual(new_seat.state, 'booked')

    def test_dashboard(self):
        self.register(self.seat('B2'))
        self.register(self.seat('B3'), state='draft', email='d@example.com')
        data = self.env['event.event'].get_seat_dashboard_data()
        self.assertEqual(data['kpis']['sold'], 1)
        self.assertEqual(data['kpis']['held'], 1)
        self.assertEqual(data['kpis']['guests'], 1)
        row = [e for e in data['events'] if e['id'] == self.event.id][0]
        self.assertEqual((row['total'], row['booked']), (31, 1))
        self.assertEqual(len(data['days']), 5)
        self.assertEqual(data['tiers'], [{'name': 'Standard', 'count': 1}])

    def test_multi_slot_refused(self):
        with self.assertRaises(ValidationError):
            self.event.is_multi_slots = True
