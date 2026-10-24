from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


def make_event(env, name='Concert', price=30.0, vip_price=80.0):
    event = env['event.event'].create({
        'name': name,
        'date_begin': fields.Datetime.now() + timedelta(days=10),
        'date_end': fields.Datetime.now() + timedelta(days=10, hours=3),
        'website_published': True,
        'event_ticket_ids': [
            (0, 0, {'name': 'Standard', 'price': price, 'product_id': env.ref('event_product.product_product_event').id,
                    'seat_rows': 4, 'seat_columns': 6, 'seat_aisle_columns': '3', 'seat_blocked': 'A1',
                    'seat_surcharge_ids': [(0, 0, {'rows': 'A', 'amount': 10.0})]}),
            (0, 0, {'name': 'VIP', 'price': vip_price, 'product_id': env.ref('event_product.product_product_event').id,
                    'seat_rows': 2, 'seat_columns': 4}),
        ],
    })
    event.event_ticket_ids.action_prepare_seats()
    return event


class SeatCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_notify_force_send=False))
        cls.event = make_event(cls.env)
        cls.standard = cls.event.event_ticket_ids.filtered(lambda t: t.name == 'Standard')
        cls.vip = cls.event.event_ticket_ids.filtered(lambda t: t.name == 'VIP')

    def seat(self, name, ticket=None):
        return (ticket or self.standard).seat_ids.filtered(lambda s: s.name == name)

    def register(self, seat, state='open', **vals):
        return self.env['event.registration'].create({
            'event_id': self.event.id, 'name': vals.pop('name', 'Guest'), 'email': vals.pop('email', 'guest@example.com'),
            'seat_id': seat.id, 'state': state, **vals})
