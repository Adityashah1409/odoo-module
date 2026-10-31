from odoo.tests.common import TransactionCase


class WarehouseCostCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_notify_force_send=False))
        cls.company = cls.env.company
        cls.company.warehouse_costing = True
        cls.wh1 = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.wh2 = cls.env['stock.warehouse'].create({'name': 'North Depot', 'code': 'NTH'})
        cls.categ = cls.env['product.category'].create({'name': 'Average costed', 'property_cost_method': 'average'})
        cls.product = cls.env['product.product'].create({
            'name': 'Copper pipe', 'default_code': 'CU-15', 'is_storable': True, 'type': 'consu',
            'categ_id': cls.categ.id, 'standard_price': 10.0})
        cls.supplier = cls.env.ref('stock.stock_location_suppliers')
        cls.customer = cls.env.ref('stock.stock_location_customers')

    def row(self, warehouse, product=None):
        return self.env['stock.warehouse.cost'].search([
            ('product_id', '=', (product or self.product).id),
            ('warehouse_id', '=', warehouse.id if warehouse else False)])

    def _move(self, source, destination, qty, product=None, **vals):
        product = product or self.product
        move = self.env['stock.move'].create({
            'product_id': product.id, 'product_uom': product.uom_id.id, 'product_uom_qty': qty,
            'location_id': source.id, 'location_dest_id': destination.id, **vals})
        move._action_confirm()
        move._action_assign()
        move.quantity = qty
        move.picked = True
        move._action_done()
        return move

    def receive(self, warehouse, qty, cost, product=None):
        product = product or self.product
        product.with_context(disable_auto_revaluation=True).standard_price = cost
        return self._move(self.supplier, warehouse.lot_stock_id, qty, product)

    def deliver(self, warehouse, qty, product=None):
        return self._move(warehouse.lot_stock_id, self.customer, qty, product)

    def transfer(self, source, destination, qty, product=None):
        return self._move(source.lot_stock_id, destination.lot_stock_id, qty, product)
