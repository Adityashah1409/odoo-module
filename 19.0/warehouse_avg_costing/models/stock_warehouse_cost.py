from collections import defaultdict

from odoo import api, fields, models

TRANSIT = 0  # bucket key of valued stock outside any warehouse (inter-warehouse transit)
FLOW_KINDS = ('in', 'out', 'transfer_in', 'transfer_out')


class StockWarehouseCost(models.Model):
    """Average cost of a product in one warehouse (the costing ledger)."""
    _name = 'stock.warehouse.cost'
    _description = 'Warehouse average cost'
    _order = 'product_id, warehouse_id'
    _rec_name = 'product_id'

    product_id = fields.Many2one('product.product', required=True, index=True, ondelete='cascade')
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id', store=True, index=True)
    categ_id = fields.Many2one(related='product_id.categ_id', store=True, string='Product Category')
    uom_id = fields.Many2one(related='product_id.uom_id', string='Unit')
    warehouse_id = fields.Many2one('stock.warehouse', index=True, ondelete='cascade',
                                   help='Empty: valued stock in transit between warehouses.')
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    quantity = fields.Float(digits='Product Unit', default=0.0, aggregator='sum')
    value = fields.Monetary(default=0.0, aggregator='sum')
    avg_cost = fields.Float('Average Cost', digits='Product Price', default=0.0, aggregator='avg')
    last_date = fields.Datetime('Last Change')
    line_ids = fields.One2many('stock.warehouse.cost.line', 'cost_id', string='History')
    location_label = fields.Char('Warehouse / Location', compute='_compute_location_label')
    company_avg_cost = fields.Float('Company Average', related='product_id.standard_price', digits='Product Price')
    cost_gap = fields.Float('Gap vs. Company (%)', compute='_compute_cost_gap', digits=(16, 1))

    _product_warehouse_unique = models.UniqueIndex('(product_id, COALESCE(warehouse_id, 0), company_id)')

    @api.depends('warehouse_id')
    def _compute_location_label(self):
        for row in self:
            row.location_label = row.warehouse_id.name or self.env._('In transit')

    @api.depends('avg_cost', 'product_id.standard_price')
    def _compute_cost_gap(self):
        for row in self:
            company_cost = row.with_company(row.company_id).product_id.standard_price
            row.cost_gap = (row.avg_cost - company_cost) / company_cost * 100 if company_cost else 0.0

    def _compute_display_name(self):
        for row in self:
            row.display_name = f'{row.product_id.display_name} @ {row.location_label}'

    # ------------------------------------------------------------------ helpers
    @api.model
    def _applicable_products(self, products, company):
        """Products valued with one average cost per warehouse in ``company``."""
        if not company.warehouse_costing:
            return products.browse()
        products = products.with_company(company)
        return products.filtered(lambda p: p.is_storable and p.cost_method == 'average' and not p.lot_valuated)

    @api.model
    def _get_row(self, product, bucket, company):
        warehouse_id = bucket or False
        row = self.sudo().search([('product_id', '=', product.id), ('warehouse_id', '=', warehouse_id),
                                  ('company_id', '=', company.id)], limit=1)
        if not row:
            row = self.sudo().create({'product_id': product.id, 'warehouse_id': warehouse_id,
                                      'company_id': company.id,
                                      'avg_cost': product.with_company(company).standard_price})
        return row

    def _book(self, quantity, unit_cost=None, kind='in', move=None, note=False, value_delta=None, adjustment=None,
              set_avg=None):
        """Change the ledger row and log a history line.

        - ``quantity`` > 0: goods come in at ``unit_cost``;
        - ``quantity`` < 0: goods leave at the current average (``unit_cost`` ignored);
        - ``value_delta``: value added without quantity (landed costs, price corrections);
        - ``set_avg``: new average for the whole quantity (adjustments, revaluations).
        """
        self.ensure_one()
        row = self.sudo()
        rounding = row.product_id.uom_id
        old_qty, old_value, old_avg = row.quantity, row.value, row.avg_cost
        currency = row.company_id.currency_id
        booked_value = 0.0
        if set_avg is not None:
            new_qty, new_avg = old_qty, set_avg
            new_value = currency.round(new_qty * new_avg)
            booked_value = new_value - old_value
            unit_cost = set_avg
        elif value_delta is not None:
            new_qty = old_qty
            if rounding.compare(old_qty, 0) > 0:
                new_value = old_value + value_delta
                new_avg = new_value / new_qty
                booked_value = value_delta
            else:
                new_value, new_avg = old_value, old_avg
                note = (note or '') + (' ' if note else '') + self.env._('(no stock left: not capitalised)')
        elif quantity > 0:
            unit_cost = unit_cost if unit_cost is not None else old_avg
            in_value = currency.round(quantity * unit_cost)
            new_qty = old_qty + quantity
            if rounding.compare(old_qty, 0) > 0:
                new_value = old_value + in_value
                new_avg = new_value / new_qty if new_qty else unit_cost
            else:
                new_avg = unit_cost
                new_value = currency.round(new_avg * new_qty)
            booked_value = in_value
        else:
            unit_cost = old_avg or row.with_company(row.company_id).product_id.standard_price
            out_value = currency.round(-quantity * unit_cost)
            new_qty = old_qty + quantity
            new_value = 0.0 if rounding.is_zero(new_qty) else old_value - out_value
            new_avg = unit_cost
            booked_value = -out_value
        row.write({'quantity': new_qty, 'value': new_value, 'avg_cost': new_avg, 'last_date': fields.Datetime.now()})
        return self.env['stock.warehouse.cost.line'].sudo().create({
            'cost_id': row.id, 'kind': kind, 'move_id': move.id if move else False,
            'adjustment_id': adjustment.id if adjustment else False,
            'quantity': quantity if set_avg is None and value_delta is None else 0.0,
            'unit_cost': unit_cost or 0.0, 'value': booked_value,
            'old_avg': old_avg, 'new_avg': new_avg, 'qty_after': new_qty, 'value_after': new_value,
            'note': note,
        })

    def action_view_history(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'warehouse_avg_costing.action_stock_warehouse_cost_line')
        action['domain'] = [('cost_id', 'in', self.ids)]
        action['name'] = self.env._('History: %s', self.display_name) if len(self) == 1 else action['name']
        return action

    # ------------------------------------------------------------------ initialisation
    @api.model
    def _initialize(self, company):
        """Rebuild the ledger of ``company`` from the quants, at the current product cost."""
        self = self.sudo().with_company(company)
        self.search([('company_id', '=', company.id)]).unlink()
        quants = self.env['stock.quant'].search([
            ('company_id', '=', company.id), ('location_id.usage', 'in', ('internal', 'transit')),
        ])
        quantities = defaultdict(float)
        for quant in quants:
            if quant.owner_id and quant.owner_id != company.partner_id:
                continue  # consigned stock is not valued
            quantities[quant.product_id, quant.location_id.warehouse_id.id or TRANSIT] += quant.quantity
        products = self._applicable_products(self.env['product.product'].concat(*{p for p, _b in quantities}), company)
        for (product, bucket), qty in quantities.items():
            if product not in products or product.uom_id.is_zero(qty):
                continue
            row = self._get_row(product, bucket, company)
            row._book(qty, product.with_company(company).standard_price, kind='init',
                      note=self.env._('Opening balance from the stock on hand'))
        return True

    # ------------------------------------------------------------------ queries
    @api.model
    def _company_totals(self, products, company):
        """{product: (quantity, value)} over all warehouses of ``company``."""
        groups = self.sudo()._read_group([('product_id', 'in', products.ids), ('company_id', '=', company.id)],
                                         ['product_id'], ['quantity:sum', 'value:sum'])
        return {product: (qty, value) for product, qty, value in groups}


class StockWarehouseCostLine(models.Model):
    """Every change of a warehouse average cost."""
    _name = 'stock.warehouse.cost.line'
    _description = 'Warehouse cost history'
    _order = 'id desc'

    cost_id = fields.Many2one('stock.warehouse.cost', required=True, index=True, ondelete='cascade')
    product_id = fields.Many2one(related='cost_id.product_id', store=True, index=True)
    categ_id = fields.Many2one(related='cost_id.categ_id', store=True)
    warehouse_id = fields.Many2one(related='cost_id.warehouse_id', store=True, index=True)
    company_id = fields.Many2one(related='cost_id.company_id', store=True, index=True)
    currency_id = fields.Many2one(related='cost_id.currency_id')
    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    user_id = fields.Many2one('res.users', default=lambda self: self.env.user)
    kind = fields.Selection([
        ('init', 'Opening balance'),
        ('in', 'Receipt'),
        ('out', 'Delivery'),
        ('transfer_in', 'Transfer in'),
        ('transfer_out', 'Transfer out'),
        ('correction', 'Value correction'),
        ('adjustment', 'Cost adjustment'),
        ('revaluation', 'Revaluation'),
    ], required=True, index=True)
    move_id = fields.Many2one('stock.move', index='btree_not_null', ondelete='set null')
    picking_id = fields.Many2one(related='move_id.picking_id', string='Transfer')
    adjustment_id = fields.Many2one('stock.warehouse.cost.adjustment', index='btree_not_null', ondelete='set null')
    quantity = fields.Float(digits='Product Unit')
    unit_cost = fields.Float(digits='Product Price')
    value = fields.Monetary(help='Value added to (or removed from) the warehouse.')
    old_avg = fields.Float('Old Average', digits='Product Price')
    new_avg = fields.Float('New Average', digits='Product Price')
    qty_after = fields.Float('Quantity After', digits='Product Unit')
    value_after = fields.Monetary('Value After')
    note = fields.Char()
    location_label = fields.Char(related='cost_id.location_label', string='Warehouse / Location')

    def _bucket(self):
        return self.cost_id.warehouse_id.id or TRANSIT
