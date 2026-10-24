from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import SeatCommon


@tagged('post_install', '-at_install')
class TestLayout(SeatCommon):

    def test_prepare_seats(self):
        seats = self.standard.seat_ids
        self.assertEqual(len(seats), 24)
        self.assertEqual(self.seat('A1').state, 'blocked')
        self.assertEqual(self.standard.seat_count, 23)
        self.assertEqual(self.standard.seats_max, 23, 'the ticket capacity follows the seats')
        self.assertTrue(self.event.seat_booking)
        a3, a4 = self.seat('A3'), self.seat('A4')
        self.assertEqual(a4.column_index - a3.column_index, 2, 'aisle after seat 3')
        self.assertEqual(self.seat('A2').surcharge, 10.0)
        self.assertEqual(self.seat('B2').surcharge, 0.0)
        self.assertEqual(self.seat('A2').price, 40.0)
        self.assertEqual(self.seat('D6').row_index, 3)
        data = self.standard._seat_map_data()
        self.assertEqual(data['width'], 7)
        self.assertEqual(len(data['rows']), 4)
        self.assertIsNone(data['rows'][0]['cells'][3], 'the aisle is an empty cell')
        self.assertTrue(data['premium'])
        self.assertIn('o_seat_blocked', str(self.standard.seat_map_preview))

    def test_rules_and_numeric_rows(self):
        self.vip.write({'seat_rows': 5, 'seat_columns': 5, 'seat_row_label': 'numeric', 'seat_aisle_rows': '2',
                        'seat_blocked': 'R3, 5, 1-1', 'seat_surcharge_ids': [(0, 0, {'rows': '1-2', 'amount': 20})]})
        self.vip.action_prepare_seats()
        names = self.vip.seat_ids.filtered(lambda s: s.state == 'blocked').mapped('name')
        self.assertIn('1-1', names)
        self.assertIn('2-5', names, 'seat number 5 blocked in every row')
        self.assertEqual(len([n for n in names if n.startswith('3-')]), 5, 'row 3 blocked')
        self.assertEqual(self.seat('2-3', self.vip).surcharge, 20)
        self.assertEqual(self.seat('3-3', self.vip).surcharge, 0)
        self.assertEqual(self.seat('3-1', self.vip).row_index - self.seat('2-1', self.vip).row_index, 2,
                         'aisle row after row 2')

    def test_layout_preview(self):
        plan = self.env['event.seat.plan'].create({'name': 'Hall', 'seat_rows': 3, 'seat_columns': 5,
                                                   'seat_aisle_columns': '2', 'seat_blocked': 'B3',
                                                   'surcharge_ids': [(0, 0, {'rows': 'A', 'amount': 4.0})]})
        data = plan._layout_map_data()
        self.assertEqual(data['width'], 6)  # 5 seats + one aisle
        cells = {c['name']: c for row in data['rows'] for c in row['cells'] if c}
        self.assertEqual((cells['B3']['status'], cells['A1']['surcharge'], cells['C5']['surcharge']),
                         ('blocked', 4.0, 0.0))
        self.assertIn('o_seat_blocked', plan.seat_map_preview)
        self.assertIn('data-seat-name="C5"', plan.seat_map_preview)

    def test_plan(self):
        plan = self.env['event.seat.plan'].create({
            'name': 'Small hall', 'seat_rows': 3, 'seat_columns': 5, 'seat_blocked': 'C5', 'seat_stage_label': 'Screen',
            'surcharge_ids': [(0, 0, {'rows': 'B-C', 'amount': 5})]})
        self.assertEqual(plan.seat_count, 14)
        self.vip.seat_plan_id = plan
        self.vip.action_apply_plan()
        self.vip.action_prepare_seats()
        self.assertEqual(len(self.vip.seat_ids), 15)
        self.assertEqual(self.seat('C2', self.vip).surcharge, 5)
        self.assertEqual(self.seat('A2', self.vip).surcharge, 0)
        self.assertEqual(self.vip._seat_map_data()['stage'], 'Screen')

    def test_rebuild_and_limits(self):
        self.register(self.seat('B2'))
        with self.assertRaises(UserError):
            self.standard.action_prepare_seats()
        with self.assertRaises(UserError):
            self.standard.action_clear_seats()
        self.vip.action_clear_seats()
        self.assertFalse(self.vip.seat_ids)
        with self.assertRaises(ValidationError):
            self.vip.write({'seat_rows': 100, 'seat_columns': 100})
        self.vip.seat_rows = 0
        with self.assertRaises(UserError):
            self.vip.action_prepare_seats()

    def test_block_unblock(self):
        b1 = self.seat('B1')
        b1.action_block()
        self.assertEqual(self.standard.seats_max, 22)
        b1.action_unblock()
        self.assertEqual(self.standard.seats_max, 23)
        self.register(self.seat('B2'))
        with self.assertRaises(UserError):
            self.seat('B2').action_block()

    def test_best_block(self):
        best = self.standard.seat_ids._best_block(2)
        self.assertEqual(best.mapped('row_label'), ['A', 'A'], 'front row first')
        self.assertIn(sorted(best.mapped('number')), ([2, 3], [4, 5]), 'side by side, near the centre')
        self.assertEqual(abs(best[0].column_index - best[1].column_index), 1, 'not split by the aisle')
        for name in ('A2', 'A3', 'A4', 'A5'):
            self.register(self.seat(name), email=f'{name}@example.com')
        best = self.standard.seat_ids._best_block(3)
        self.assertEqual(best.mapped('row_label'), ['B', 'B', 'B'])
        self.assertEqual(len(self.standard.seat_ids._best_block(30)), 0, 'not enough seats')
        for name in ('B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'C1', 'C2', 'C4', 'C5', 'C6'):
            if self.seat(name).state == 'available':
                self.register(self.seat(name), email=f'{name}@example.com')
        self.assertEqual(self.standard.seat_ids._best_block(4).mapped('name'), ['D2', 'D3', 'D4', 'D5'],
                         'no 4 seats side by side: 4 in a row across the aisle, centred')
