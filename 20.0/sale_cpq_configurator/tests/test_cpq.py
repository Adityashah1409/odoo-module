from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestCpq(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env['product.product']

        def component(name, price):
            return Product.create({'name': name, 'lst_price': price, 'is_storable': True})
        cls.top_oak = component('Top oak 160x80', 300)
        cls.top_glass = component('Top glass 160x80', 450)
        cls.legs_steel = component('Steel frame', 200)
        cls.legs_motor = component('Motorized frame', 600)
        cls.cable_tray = component('Cable tray', 40)
        cls.drawer = component('Drawer unit', 120)
        cls.desk = cls.env['product.template'].create({'name': 'Custom desk', 'type': 'consu'})
        cls.workcenter = cls.env['mrp.workcenter'].create({'name': 'Desk assembly'})
        cls.configurator = cls.env['cpq.configurator'].create({
            'name': 'Custom desk', 'product_tmpl_id': cls.desk.id, 'base_price': 100.0, 'bom_type': 'normal',
        })
        Section = cls.env['cpq.section']
        cls.s_top = Section.create({'name': 'Top', 'configurator_id': cls.configurator.id, 'sequence': 1})
        cls.s_frame = Section.create({'name': 'Frame', 'configurator_id': cls.configurator.id, 'sequence': 2})
        cls.s_extras = Section.create({'name': 'Extras', 'configurator_id': cls.configurator.id, 'sequence': 3,
                                       'selection': 'multi', 'required': False})

        def option(section, product, **values):
            return cls.env['cpq.option'].create(dict({
                'configurator_id': cls.configurator.id, 'section_id': section.id, 'product_id': product.id}, **values))
        cls.o_oak = option(cls.s_top, cls.top_oak, default_selected=True)
        cls.o_glass = option(cls.s_top, cls.top_glass)
        cls.o_steel = option(cls.s_frame, cls.legs_steel, default_selected=True)
        cls.o_motor = option(cls.s_frame, cls.legs_motor)
        cls.o_tray = option(cls.s_extras, cls.cable_tray, visible_if_option_ids=[(6, 0, cls.o_motor.ids)])
        cls.o_drawer = option(cls.s_extras, cls.drawer, max_qty=2, unit_price=110)
        cls.o_glass.excluded_option_ids = cls.o_motor
        cls.env['cpq.price.rule'].create([
            {'name': 'Motorized assembly', 'configurator_id': cls.configurator.id, 'rule_type': 'fixed',
             'amount': 50, 'condition_option_ids': [(6, 0, cls.o_motor.ids)], 'sequence': 1},
            {'name': 'Volume discount', 'configurator_id': cls.configurator.id, 'rule_type': 'discount',
             'amount': 10, 'min_quantity': 5, 'sequence': 2},
        ])
        cls.env['cpq.operation'].create([
            {'name': 'Assemble desk', 'configurator_id': cls.configurator.id, 'workcenter_id': cls.workcenter.id,
             'duration': 45},
            {'name': 'Install motor', 'configurator_id': cls.configurator.id, 'workcenter_id': cls.workcenter.id,
             'duration': 20, 'option_ids': [(6, 0, cls.o_motor.ids)]},
        ])
        cls.customer = cls.env['res.partner'].create({'name': 'Office Works'})

    def new_order(self):
        return self.env['sale.order'].create({'partner_id': self.customer.id})

    def wizard(self, order=None, quantity=1.0):
        return self.env['cpq.configure.wizard'].create({
            'order_id': (order or self.new_order()).id, 'configurator_id': self.configurator.id, 'quantity': quantity})

    def select(self, wizard, *options, qty=None):
        for line in wizard.line_ids:
            if line.option_id in options:
                line.selected = True
                if qty:
                    line.quantity = qty

    def unselect(self, wizard, *options):
        wizard.line_ids.filtered(lambda l: l.option_id in options).selected = False

    def test_defaults_and_price(self):
        wizard = self.wizard()
        self.assertEqual(wizard.line_ids.filtered('selected').option_id, self.o_oak | self.o_steel)
        self.assertEqual(wizard.total_price, 100 + 300 + 200)
        self.assertFalse(wizard.problems)
        self.assertIn('Base price', wizard.breakdown_html)

    def test_price_rules(self):
        wizard = self.wizard(quantity=5)
        self.unselect(wizard, self.o_steel)
        self.select(wizard, self.o_motor)
        self.select(wizard, self.o_drawer, qty=2)
        # 100 + 300 + 600 + 2 × 110 = 1220, + 50 (motor) = 1270, -10 % (qty ≥ 5) = 1143
        self.assertAlmostEqual(wizard.total_price, 1143.0)
        self.assertIn('Volume discount', wizard.breakdown_html)

    def test_rules(self):
        wizard = self.wizard()
        self.unselect(wizard, self.o_oak)
        self.assertIn('Top: choose an option', wizard.problems)
        self.select(wizard, self.o_oak, self.o_glass)
        self.assertIn('only one option', wizard.problems)
        self.unselect(wizard, self.o_oak, self.o_steel)
        self.select(wizard, self.o_motor)
        self.assertIn('not compatible', wizard.problems)
        self.unselect(wizard, self.o_glass)
        self.select(wizard, self.o_oak)
        self.select(wizard, self.o_drawer, qty=3)
        self.assertIn('between', wizard.problems)
        with self.assertRaises(UserError):
            wizard.action_add_to_order()

    def test_visibility(self):
        wizard = self.wizard()
        tray = wizard.line_ids.filtered(lambda l: l.option_id == self.o_tray)
        self.assertFalse(tray.available)
        tray.selected = True
        self.assertIn('only available with', wizard.problems)
        self.unselect(wizard, self.o_steel)
        self.select(wizard, self.o_motor)
        self.assertTrue(tray.available)
        self.assertFalse(wizard.problems)

    def test_add_to_quotation_creates_product_and_bom(self):
        order = self.new_order()
        wizard = self.wizard(order, quantity=2)
        self.unselect(wizard, self.o_steel)
        self.select(wizard, self.o_motor, self.o_tray)
        wizard.action_add_to_order()
        line = order.order_line
        config = line.cpq_configuration_id
        self.assertEqual((line.product_uom_qty, line.price_unit), (2, 100 + 300 + 600 + 40 + 50))
        self.assertIn('Frame: Motorized frame', line.name)
        self.assertTrue(config.name.startswith('CPQ'))
        self.assertEqual(config.product_id, line.product_id)
        self.assertIn(config.name, config.product_id.display_name)
        bom = config.bom_id
        self.assertEqual(bom.type, 'normal')
        self.assertEqual(bom.bom_line_ids.product_id, self.top_oak | self.legs_motor | self.cable_tray)
        self.assertEqual(sorted(bom.operation_ids.mapped('name')), ['Assemble desk', 'Install motor'])
        # the configured price survives pricelist recomputation
        line.product_uom_qty = 3
        self.assertEqual(line.price_unit, 1090)

    def test_confirm_creates_manufacturing_order(self):
        order = self.new_order()
        self.wizard(order, quantity=2).action_add_to_order()
        order.action_confirm()
        config = order.cpq_configuration_ids
        production = config.production_ids
        self.assertEqual(config.state, 'confirmed')
        self.assertEqual(len(production), 1)
        self.assertEqual(production.product_qty, 2)
        self.assertEqual(production.state, 'confirmed')
        self.assertEqual(production.move_raw_ids.product_id, self.top_oak | self.legs_steel)
        self.assertEqual(production.origin, order.name)
        self.assertEqual(order.cpq_production_count, 1)

    def test_kit_configuration(self):
        self.configurator.bom_type = 'phantom'
        order = self.new_order()
        self.wizard(order).action_add_to_order()
        order.action_confirm()
        config = order.cpq_configuration_ids
        self.assertEqual(config.bom_id.type, 'phantom')
        self.assertFalse(config.production_ids)
        self.assertEqual(order.picking_ids.move_ids.product_id, self.top_oak | self.legs_steel)

    def test_cancel_and_confirmed_orders(self):
        order = self.new_order()
        self.wizard(order).action_add_to_order()
        order._action_cancel()
        self.assertEqual(order.cpq_configuration_ids.state, 'cancel')
        confirmed = self.new_order()
        confirmed.action_confirm()
        with self.assertRaises(UserError):
            self.wizard(confirmed).action_add_to_order()

    def test_wizard_from_sale_order_form(self):
        order = self.new_order()
        action = order.action_cpq_configure()
        form = Form(self.env['cpq.configure.wizard'].with_context(action['context']))
        form.configurator_id = self.configurator
        self.assertEqual(form.total_price, 600)
        wizard = form.save()
        wizard.action_add_to_order()
        self.assertEqual(order.cpq_configuration_count, 1)

    def test_stock_availability(self):
        self.env['stock.quant']._update_available_quantity(
            self.top_oak, self.env.ref('stock.warehouse0').lot_stock_id, 3)
        wizard = self.wizard(quantity=5)
        oak = wizard.line_ids.filtered(lambda l: l.option_id == self.o_oak)
        self.assertEqual(oak.stock_qty, 3)
        self.assertFalse(oak.stock_ok)

    def test_access(self):
        salesman = new_test_user(self.env, 'cpq_sales', groups='sales_team.group_sale_salesman')
        self.assertTrue(self.configurator.with_user(salesman).name)
        with self.assertRaises(AccessError):
            self.configurator.with_user(salesman).base_price = 1
