from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    warehouse_cost_ids = fields.One2many('stock.warehouse.cost', 'product_id', string='Warehouse Costs')

    def _wh_sync_standard_price(self):
        """Company cost = weighted average of the warehouse costs (quantity-weighted)."""
        Cost = self.env['stock.warehouse.cost']
        company = self.env.company
        products = Cost._applicable_products(self, company)
        if not products:
            return
        totals = Cost._company_totals(products, company)
        for product in products:
            qty, value = totals.get(product, (0.0, 0.0))
            if product.uom_id.compare(qty, 0) <= 0:
                continue
            price = value / qty
            if product.standard_price != price:
                product.sudo().with_context(disable_auto_revaluation=True, mail_notrack=True).standard_price = price

    def _update_standard_price(self, *args, **kwargs):
        result = super()._update_standard_price(*args, **kwargs)
        self._wh_sync_standard_price()
        return result

    def write(self, vals):
        manual_price = 'standard_price' in vals and not self.env.context.get('disable_auto_revaluation')
        res = super().write(vals)
        if manual_price:
            # a manual cost update revalues the product in every warehouse
            Cost = self.env['stock.warehouse.cost'].sudo()
            company = self.env.company
            for product in Cost._applicable_products(self, company):
                rows = Cost.search([('product_id', '=', product.id), ('company_id', '=', company.id)])
                for row in rows:
                    row._book(0.0, kind='revaluation', set_avg=vals['standard_price'],
                              note=self.env._('Product cost changed to %s', vals['standard_price']))
            self._wh_sync_standard_price()
        return res

    @api.depends_context('to_date', 'company', 'warehouse_id')
    def _compute_value(self):
        super()._compute_value()
        warehouse_id = self.env.context.get('warehouse_id')
        if not warehouse_id or self.env.context.get('to_date') or not isinstance(warehouse_id, int):
            return
        Cost = self.env['stock.warehouse.cost'].sudo()
        products = Cost._applicable_products(self, self.env.company)
        if not products:
            return
        rows = Cost.search([('product_id', 'in', products.ids), ('warehouse_id', '=', warehouse_id),
                            ('company_id', '=', self.env.company.id)])
        by_product = {row.product_id: row for row in rows}
        for product in self:
            row = by_product.get(product)
            if product in products and row:
                product.total_value = row.value
                product.avg_cost = row.avg_cost

    def _correct_inventory_valuation(self, from_date):
        """Odoo 20 replays the company average when a past incoming value changes. Products valued per warehouse
        keep the cost their warehouse had: the new value goes into that warehouse instead (see stock.move)."""
        warehouse_costed = self.env['stock.warehouse.cost']._applicable_products(self, self.env.company)
        return super(ProductProduct, self - warehouse_costed)._correct_inventory_valuation(from_date)

    def action_view_warehouse_costs(self):
        action = self.env['ir.actions.act_window']._for_xml_id('warehouse_avg_costing.action_stock_warehouse_cost')
        action['domain'] = [('product_id', 'in', self.ids)]
        action['context'] = {'search_default_group_product': 0}
        return action

    def action_view_cost_history(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'warehouse_avg_costing.action_stock_warehouse_cost_line')
        action['domain'] = [('product_id', 'in', self.ids)]
        return action


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    warehouse_cost_ids = fields.Many2many('stock.warehouse.cost', compute='_compute_warehouse_cost_ids',
                                          string='Warehouse Costs')
    warehouse_costing_active = fields.Boolean(compute='_compute_warehouse_cost_ids')

    @api.depends('product_variant_ids')
    @api.depends_context('company')
    def _compute_warehouse_cost_ids(self):
        Cost = self.env['stock.warehouse.cost']
        company = self.env.company
        rows = Cost.search([('product_tmpl_id', 'in', self.ids), ('company_id', '=', company.id)])
        for template in self:
            template.warehouse_cost_ids = rows.filtered(lambda r: r.product_tmpl_id == template)
            template.warehouse_costing_active = bool(
                Cost._applicable_products(template.product_variant_ids, company))

    def action_view_warehouse_costs(self):
        return self.product_variant_ids.action_view_warehouse_costs()

    def action_view_cost_history(self):
        return self.product_variant_ids.action_view_cost_history()
