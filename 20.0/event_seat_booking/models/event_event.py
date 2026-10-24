from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class EventEvent(models.Model):
    _inherit = 'event.event'

    seat_booking = fields.Boolean('Seat booking', help='Attendees choose their seat on a seat map.')
    seat_ids = fields.One2many('event.seat', 'event_id', string='Seats')
    seat_waitlist_ids = fields.One2many('event.seat.waitlist', 'event_id', string='Waitlist')
    seat_total = fields.Integer('Total Seats', compute='_compute_seat_totals')
    seat_booked = fields.Integer('Booked seats', compute='_compute_seat_totals')
    seat_free = fields.Integer('Free seats', compute='_compute_seat_totals')
    seat_occupancy = fields.Float('Occupancy (%)', compute='_compute_seat_totals')
    seat_waitlist_count = fields.Integer('Waiting', compute='_compute_seat_totals')

    @api.constrains('seat_booking', 'is_multi_slots')
    def _check_seat_booking_slots(self):
        for event in self:
            if event.seat_booking and event.is_multi_slots:
                raise ValidationError(self.env._('Seat booking cannot be combined with time slots.'))

    def _compute_seat_totals(self):
        groups = self.env['event.seat']._read_group([('event_id', 'in', self.ids)], ['event_id', 'state'], ['__count'])
        stats = {}
        for event, state, count in groups:
            stats.setdefault(event.id, {})[state] = count
        waiting = dict(self.env['event.seat.waitlist']._read_group(
            [('event_id', 'in', self.ids), ('state', '=', 'waiting')], ['event_id'], ['__count']))
        for event in self:
            values = stats.get(event.id, {})
            total = sum(c for s, c in values.items() if s != 'blocked')
            event.seat_total = total
            event.seat_booked = values.get('booked', 0)
            event.seat_free = values.get('available', 0)
            event.seat_occupancy = 100.0 * event.seat_booked / total if total else 0.0
            event.seat_waitlist_count = waiting.get(event, 0)

    def _seat_sold_out(self):
        self.ensure_one()
        return self.seat_booking and bool(self.seat_ids) and not self.seat_ids.filtered(
            lambda s: s._is_free_for(None) and s.ticket_id.sale_available)

    def _seat_waitlist_notify(self, count):
        """Tell the first ``count`` people waiting that seats are free again."""
        for event in self:
            waiting = event.seat_waitlist_ids.filtered(lambda w: w.state == 'waiting').sorted('id')[:count]
            waiting._notify()

    def action_view_seats(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('event_seat_booking.action_event_seat')
        action.update({'domain': [('event_id', '=', self.id)], 'context': {'search_default_group_ticket': 1}})
        return action

    def action_view_waitlist(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('event_seat_booking.action_event_seat_waitlist')
        action.update({'domain': [('event_id', '=', self.id)], 'context': {'default_event_id': self.id}})
        return action

    @api.model
    def get_seat_dashboard_data(self):
        """Seating KPIs for the dashboard (events with seat booking the user can read)."""
        events = self.search([('seat_booking', '=', True)])
        Seat = self.env['event.seat']
        now = fields.Datetime.now()
        states = dict(Seat._read_group([('event_id', 'in', events.ids)], ['state'], ['__count']))
        sellable = sum(c for s, c in states.items() if s != 'blocked')
        lines = self.env['sale.order.line'].sudo().search([
            ('order_id.state', '=', 'sale'), '|', ('event_id', 'in', events.ids), ('seat_id.event_id', 'in', events.ids)])
        revenue_by_event = {}
        revenue_by_day = {}
        start_day = fields.Date.context_today(self) - timedelta(days=4)
        for line in lines:
            event = line.event_id or line.seat_id.event_id
            revenue_by_event[event.id] = revenue_by_event.get(event.id, 0.0) + line.price_subtotal
            day = fields.Datetime.context_timestamp(self, line.order_id.date_order).date()
            if day >= start_day:
                revenue_by_day[day] = revenue_by_day.get(day, 0.0) + line.price_subtotal
        registrations = self.env['event.registration'].search([('event_id', 'in', events.ids), ('seat_id', '!=', False),
                                                               ('state', 'in', ('open', 'done'))])
        tiers = {}
        for name, count in Seat._read_group([('event_id', 'in', events.ids), ('state', '=', 'booked')], ['ticket_id'],
                                            ['__count']):
            tiers[name.name] = tiers.get(name.name, 0) + count
        recent = self.env['event.registration'].search([('event_id', 'in', events.ids), ('seat_id', '!=', False)],
                                                       order='create_date desc, id desc', limit=8)
        currency = self.env.company.currency_id
        return {
            'currency': {'symbol': currency.symbol, 'position': currency.position},
            'kpis': {
                'revenue': sum(revenue_by_event.values()),
                'sold': states.get('booked', 0),
                'held': states.get('held', 0),
                'free': states.get('available', 0),
                'occupancy': round(100.0 * states.get('booked', 0) / sellable, 1) if sellable else 0,
                'yield': round(sum(revenue_by_event.values()) / states.get('booked', 1), 2) if states.get('booked') else 0,
                'active_events': len(events.filtered(lambda e: e.date_end and e.date_end >= now)),
                'guests': len(set(filter(None, registrations.mapped('email')))),
                'waiting': self.env['event.seat.waitlist'].search_count([('event_id', 'in', events.ids),
                                                                         ('state', '=', 'waiting')]),
            },
            'status': [{'key': key, 'count': states.get(key, 0)} for key in ('booked', 'held', 'available', 'blocked')],
            'days': [{'day': fields.Date.to_string(start_day + timedelta(days=i)),
                      'amount': revenue_by_day.get(start_day + timedelta(days=i), 0.0)} for i in range(5)],
            'tiers': sorted([{'name': n, 'count': c} for n, c in tiers.items()], key=lambda t: -t['count']),
            'events': sorted([{
                'id': e.id, 'name': e.name, 'date': fields.Datetime.to_string(e.date_begin),
                'total': e.seat_total, 'booked': e.seat_booked, 'free': e.seat_free,
                'occupancy': round(e.seat_occupancy, 1), 'revenue': revenue_by_event.get(e.id, 0.0),
                'waiting': e.seat_waitlist_count,
            } for e in events], key=lambda e: -e['revenue']),
            'recent': [{'id': r.id, 'name': r.name, 'seat': r.seat_id.name, 'section': r.seat_id.ticket_id.name,
                        'event': r.event_id.name, 'state': r.state,
                        'date': fields.Datetime.to_string(r.create_date)} for r in recent],
        }
