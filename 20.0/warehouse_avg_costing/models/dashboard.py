from datetime import timedelta

from odoo import api, fields, models


class StockWarehouseCostDashboard(models.AbstractModel):
    _name = 'stock.warehouse.cost.dashboard'
    _description = 'Warehouse costing dashboard'

    @api.model
    def get_data(self):
        company = self.env.company
        Cost = self.env['stock.warehouse.cost']
        Line = self.env['stock.warehouse.cost.line']
        rows = Cost.search([('company_id', '=', company.id)])
        since = fields.Datetime.now() - timedelta(days=30)
        warehouses = []
        for warehouse_id, quantity, value, count in Cost._read_group(
                [('company_id', '=', company.id)], ['warehouse_id'], ['quantity:sum', 'value:sum', '__count']):
            warehouses.append({'id': warehouse_id.id, 'name': warehouse_id.name or self.env._('In transit'),
                               'code': warehouse_id.code or '—', 'value': value, 'products': count})
        warehouses.sort(key=lambda w: -w['value'])
        spreads = []
        for product, product_rows in rows.filtered(lambda r: r.quantity > 0).grouped('product_id').items():
            if len(product_rows) < 2:
                continue
            low, high = min(product_rows.mapped('avg_cost')), max(product_rows.mapped('avg_cost'))
            spreads.append({'id': product.id, 'name': product.display_name, 'low': low, 'high': high,
                            'spread': round((high - low) / low * 100, 1) if low else 0.0,
                            'warehouses': len(product_rows)})
        spreads.sort(key=lambda s: -s['spread'])
        categories = []
        for categ, value in Cost._read_group([('company_id', '=', company.id)], ['categ_id'], ['value:sum']):
            categories.append({'name': categ.display_name or self.env._('None'), 'value': value})
        categories.sort(key=lambda c: -c['value'])
        recent = Line.search([('company_id', '=', company.id), ('kind', '!=', 'init')], limit=8)
        kinds = dict(Line._fields['kind']._description_selection(self.env))
        return {
            'currency': {'symbol': company.currency_id.symbol, 'position': company.currency_id.position},
            'kpis': {
                'value': sum(rows.mapped('value')),
                'warehouses': len([w for w in warehouses if w['value']]),
                'products': len(rows.filtered(lambda r: r.quantity > 0).product_id),
                'changes': Line.search_count([('company_id', '=', company.id), ('date', '>=', since),
                                              ('kind', '!=', 'init')]),
                'pending': self.env['stock.warehouse.cost.adjustment'].search_count(
                    [('company_id', '=', company.id), ('state', '=', 'to_approve')]),
                'enabled': company.warehouse_costing,
            },
            'warehouses': warehouses,
            'spreads': spreads[:8],
            'categories': categories[:6],
            'recent': [{
                'id': line.id, 'product': line.product_id.display_name, 'warehouse': line.location_label,
                'kind': kinds.get(line.kind), 'kind_key': line.kind, 'old': line.old_avg, 'new': line.new_avg,
                'quantity': line.quantity, 'date': fields.Datetime.to_string(line.date),
            } for line in recent],
        }
