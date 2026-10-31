from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import WarehouseCostCommon


@tagged('post_install', '-at_install')
class TestWarehouseCosting(WarehouseCostCommon):

    def test_receipts_keep_one_cost_per_warehouse(self):
        self.receive(self.wh1, 100, 10.0)
        self.receive(self.wh2, 50, 14.0)
        self.assertEqual((self.row(self.wh1).quantity, self.row(self.wh1).avg_cost), (100, 10.0))
        self.assertEqual((self.row(self.wh2).quantity, self.row(self.wh2).avg_cost), (50, 14.0))
        self.assertAlmostEqual(self.product.standard_price, 1700 / 150, places=4,
                               msg='company cost = quantity-weighted average of the warehouses')
        self.receive(self.wh1, 100, 13.0)
        self.assertAlmostEqual(self.row(self.wh1).avg_cost, 11.5)
        self.assertEqual(self.row(self.wh2).avg_cost, 14.0, 'other warehouse untouched')
        kinds = self.env['stock.warehouse.cost.line'].search([('product_id', '=', self.product.id)]).mapped('kind')
        self.assertEqual(set(kinds), {'in'})

    def test_delivery_leaves_at_its_warehouse_cost(self):
        self.receive(self.wh1, 100, 10.0)
        self.receive(self.wh2, 50, 14.0)
        out = self.deliver(self.wh2, 30)
        self.assertAlmostEqual(out.value, 420.0, msg='cost of goods sold at the cost of the warehouse')
        self.assertEqual((self.row(self.wh2).quantity, self.row(self.wh2).value), (20, 280.0))
        self.assertAlmostEqual(self.product.standard_price, 1280 / 120, places=4)
        out = self.deliver(self.wh1, 10)
        self.assertAlmostEqual(out.value, 100.0)
        line = self.env['stock.warehouse.cost.line'].search([('move_id', '=', out.id)])
        self.assertEqual((line.kind, line.quantity, line.unit_cost), ('out', -10, 10.0))

    def test_inter_warehouse_transfer_carries_the_cost(self):
        self.receive(self.wh1, 100, 10.0)
        self.receive(self.wh2, 50, 14.0)
        before = self.product.standard_price
        move = self.transfer(self.wh1, self.wh2, 50)
        self.assertEqual((self.row(self.wh1).quantity, self.row(self.wh1).value), (50, 500.0))
        self.assertEqual((self.row(self.wh2).quantity, self.row(self.wh2).value), (100, 1200.0))
        self.assertAlmostEqual(self.row(self.wh2).avg_cost, 12.0)
        self.assertAlmostEqual(self.product.standard_price, before, msg='company value does not change')
        kinds = self.env['stock.warehouse.cost.line'].search([('move_id', '=', move.id)]).mapped('kind')
        self.assertEqual(sorted(kinds), ['transfer_in', 'transfer_out'])
        # a move inside one warehouse changes nothing
        shelf = self.env['stock.location'].create({'name': 'Shelf A', 'location_id': self.wh1.lot_stock_id.id})
        inside = self._move(self.wh1.lot_stock_id, shelf, 5)
        self.assertFalse(self.env['stock.warehouse.cost.line'].search([('move_id', '=', inside.id)]))

    def test_two_step_transit(self):
        self.receive(self.wh1, 40, 9.0)
        self.receive(self.wh2, 10, 15.0)
        transit = self.env['stock.location'].create({'name': 'Truck', 'usage': 'transit',
                                                     'company_id': self.company.id})
        first = self._move(self.wh1.lot_stock_id, transit, 20)
        self.assertEqual((self.row(False).quantity, self.row(False).value), (20, 180.0), 'valued while in transit')
        self._move(transit, self.wh2.lot_stock_id, 20, move_orig_ids=[(6, 0, first.ids)])
        self.assertEqual(self.row(False).quantity, 0)
        self.assertEqual((self.row(self.wh2).quantity, self.row(self.wh2).value), (30, 330.0))

    def test_value_correction_after_receipt(self):
        receipt = self.receive(self.wh1, 100, 10.0)
        self.receive(self.wh2, 100, 10.0)
        self.env['product.value'].create({'move_id': receipt.id, 'value': 1200.0, 'company_id': self.company.id})
        self.assertAlmostEqual(receipt.value, 1200.0)
        self.assertAlmostEqual(self.row(self.wh1).avg_cost, 12.0, msg='landed cost / bill difference in WH1 only')
        self.assertAlmostEqual(self.row(self.wh2).avg_cost, 10.0)
        line = self.env['stock.warehouse.cost.line'].search([('move_id', '=', receipt.id), ('kind', '=', 'correction')])
        self.assertAlmostEqual(line.value, 200.0)
        self.assertAlmostEqual(self.product.standard_price, 11.0)

    def test_manual_cost_change_revalues_every_warehouse(self):
        self.receive(self.wh1, 10, 10.0)
        self.receive(self.wh2, 10, 20.0)
        self.product.standard_price = 18.0
        self.assertEqual((self.row(self.wh1).avg_cost, self.row(self.wh2).avg_cost), (18.0, 18.0))
        self.assertEqual(self.row(self.wh1).value, 180.0)
        self.assertEqual(self.product.standard_price, 18.0)
        self.assertEqual(self.row(self.wh1).line_ids.sorted('id')[-1].kind, 'revaluation')

    def test_negative_stock(self):
        self.receive(self.wh1, 10, 10.0)
        out = self.deliver(self.wh2, 5)  # nothing in the second warehouse yet
        self.assertEqual(self.row(self.wh2).quantity, -5)
        self.assertAlmostEqual(out.value, 50.0, msg='falls back to the company cost')
        self.receive(self.wh2, 15, 16.0)
        self.assertEqual((self.row(self.wh2).quantity, self.row(self.wh2).avg_cost), (10, 16.0))
        self.assertAlmostEqual(self.row(self.wh2).value, 160.0)

    def test_cost_adjustment_with_approval(self):
        self.company.warehouse_cost_approval = True
        self.receive(self.wh1, 10, 10.0)
        self.receive(self.wh2, 10, 10.0)
        clerk = new_test_user(self.env, 'wh_clerk', groups='stock.group_stock_user')
        Adjustment = self.env['stock.warehouse.cost.adjustment']
        request = Adjustment.with_user(clerk).create({'product_id': self.product.id, 'warehouse_id': self.wh2.id,
                                                      'new_cost': 13.0, 'reason': 'Freight not on the bill'})
        self.assertTrue(request.name.startswith('WCA/'))
        self.assertEqual((request.current_cost, request.value_change), (10.0, 30.0))
        request.action_submit()
        self.assertEqual(request.state, 'to_approve')
        self.assertEqual(self.row(self.wh2).avg_cost, 10.0, 'not applied before approval')
        with self.assertRaises(UserError):
            request.with_user(clerk).action_approve()
        request = request.with_env(self.env)
        request.action_approve()
        self.assertEqual((request.state, request.old_cost, self.row(self.wh2).avg_cost), ('done', 10.0, 13.0))
        self.assertAlmostEqual(self.product.standard_price, 11.5)
        self.assertIn('11.5', request.message_ids[0].body)
        # a manager applies directly
        direct = Adjustment.create({'product_id': self.product.id, 'warehouse_id': self.wh1.id, 'new_cost': 9.0})
        direct.action_submit()
        self.assertEqual(direct.state, 'done')
        refused = Adjustment.with_user(clerk).create({'product_id': self.product.id, 'warehouse_id': self.wh1.id,
                                                      'new_cost': 99.0})
        refused.action_submit()
        refused.with_env(self.env).action_refuse()
        self.assertEqual((refused.state, self.row(self.wh1).avg_cost), ('refused', 9.0))

    def test_initialize_from_stock_on_hand(self):
        self.company.warehouse_costing = False
        Quant = self.env['stock.quant']
        Quant._update_available_quantity(self.product, self.wh1.lot_stock_id, 30)
        Quant._update_available_quantity(self.product, self.wh2.lot_stock_id, 20)
        self.assertFalse(self.row(self.wh1))
        settings = self.env['res.config.settings'].create({'warehouse_costing': True})
        settings.execute()
        self.assertEqual((self.row(self.wh1).quantity, self.row(self.wh1).avg_cost), (30, 10.0))
        self.assertEqual(self.row(self.wh2).quantity, 20)
        self.assertEqual(self.row(self.wh1).line_ids.mapped('kind'), ['init'])

    def test_not_applicable(self):
        fifo = self.env['product.category'].create({'name': 'FIFO', 'property_cost_method': 'fifo'})
        other = self.env['product.product'].create({'name': 'Bolt', 'is_storable': True, 'type': 'consu',
                                                    'categ_id': fifo.id})
        self.receive(self.wh1, 5, 3.0, product=other)
        self.assertFalse(self.row(self.wh1, other))
        self.company.warehouse_costing = False
        self.receive(self.wh1, 5, 3.0)
        self.assertFalse(self.row(self.wh1))

    def test_valuation_per_warehouse_context(self):
        self.receive(self.wh1, 100, 10.0)
        self.receive(self.wh2, 50, 14.0)
        product = self.product.with_context(warehouse_id=self.wh2.id)
        self.assertAlmostEqual(product.total_value, 700.0)
        self.assertAlmostEqual(product.avg_cost, 14.0)
        self.assertAlmostEqual(self.product.total_value, 1700.0)

    def test_history_dates(self):
        with freeze_time('2026-01-05 10:00:00'):
            self.receive(self.wh1, 10, 10.0)
        line = self.row(self.wh1).line_ids
        self.assertEqual(fields.Datetime.to_string(line.date), '2026-01-05 10:00:00')
