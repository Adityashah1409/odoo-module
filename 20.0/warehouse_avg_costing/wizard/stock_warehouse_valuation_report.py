import base64
import io

import xlsxwriter

from odoo import fields, models


class StockWarehouseValuationReport(models.TransientModel):
    _name = 'stock.warehouse.valuation.report'
    _description = 'Warehouse valuation report'

    report_type = fields.Selection([
        ('summary', 'Summary per warehouse'),
        ('detailed', 'Detailed (product × warehouse)'),
        ('comparison', 'Cost comparison between warehouses'),
    ], default='summary', required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses', domain="[('company_id', '=', company_id)]",
                                     help='Empty: all warehouses.')
    categ_ids = fields.Many2many('product.category', string='Product Categories', help='Empty: all categories.')
    include_empty = fields.Boolean('Include products without stock')
    xlsx_file = fields.Binary(readonly=True, attachment=False)
    xlsx_name = fields.Char()

    def _domain(self):
        domain = [('company_id', '=', self.company_id.id)]
        if self.warehouse_ids:
            domain.append(('warehouse_id', 'in', self.warehouse_ids.ids))
        if self.categ_ids:
            domain.append(('categ_id', 'child_of', self.categ_ids.ids))
        if not self.include_empty:
            domain.append(('quantity', '!=', 0))
        return domain

    def _report_data(self):
        """Everything the screen, Excel and PDF versions show."""
        self.ensure_one()
        rows = self.env['stock.warehouse.cost'].search(self._domain())
        total_value = sum(rows.mapped('value'))
        warehouses = rows.mapped('warehouse_id').sorted('name')
        columns = [{'id': w.id, 'name': w.name, 'code': w.code} for w in warehouses]
        if rows.filtered(lambda r: not r.warehouse_id):
            columns.append({'id': False, 'name': self.env._('In transit'), 'code': self.env._('Transit')})
        summary = []
        for column in columns:
            group = rows.filtered(lambda r: (r.warehouse_id.id or False) == column['id'])
            value = sum(group.mapped('value'))
            summary.append({**column, 'products': len(group.product_id), 'quantity': sum(group.mapped('quantity')),
                            'value': value, 'share': round(value / total_value * 100, 1) if total_value else 0.0})
        detailed = [{
            'warehouse': row.location_label, 'code': row.product_id.default_code or '',
            'product': row.product_id.display_name, 'category': row.categ_id.display_name or '',
            'quantity': row.quantity, 'uom': row.uom_id.name, 'avg_cost': row.avg_cost, 'value': row.value,
            'company_cost': row.with_company(row.company_id).product_id.standard_price, 'gap': row.cost_gap,
        } for row in rows.sorted(lambda r: (r.location_label, r.product_id.display_name))]
        comparison = []
        for product, product_rows in rows.grouped('product_id').items():
            costs = {(r.warehouse_id.id or False): r.avg_cost for r in product_rows}
            values = [c for c in costs.values() if c]
            low, high = (min(values), max(values)) if values else (0.0, 0.0)
            comparison.append({
                'code': product.default_code or '', 'product': product.display_name,
                'costs': [costs.get(column['id']) for column in columns],
                'company_cost': product.with_company(self.company_id).standard_price,
                'low': low, 'high': high, 'spread': round((high - low) / low * 100, 1) if low else 0.0,
            })
        comparison.sort(key=lambda c: -c['spread'])
        return {
            'company': self.company_id.name, 'currency': self.company_id.currency_id,
            'date': fields.Datetime.context_timestamp(self, fields.Datetime.now()),
            'report_type': self.report_type,
            'title': dict(self._fields['report_type']._description_selection(self.env))[self.report_type],
            'columns': columns, 'summary': summary, 'detailed': detailed, 'comparison': comparison,
            'total_value': total_value, 'total_quantity': sum(rows.mapped('quantity')),
        }

    def action_view(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('warehouse_avg_costing.action_stock_warehouse_cost')
        action['domain'] = self._domain()
        if self.report_type == 'summary':
            action.update(view_mode='pivot,list', views=[(False, 'pivot'), (False, 'list')])
        elif self.report_type == 'comparison':
            action.update(view_mode='pivot,list', views=[(False, 'pivot'), (False, 'list')],
                          context={'pivot_measures': ['avg_cost'], 'pivot_row_groupby': ['product_id'],
                                   'pivot_column_groupby': ['warehouse_id']})
        else:
            action.update(view_mode='list,pivot', views=[(False, 'list'), (False, 'pivot')],
                          context={'search_default_group_warehouse': 1})
        return action

    def action_pdf(self):
        return self.env.ref('warehouse_avg_costing.action_report_warehouse_valuation').report_action(self)

    def action_xlsx(self):
        self.ensure_one()
        data = self._report_data()
        buffer = io.BytesIO()
        book = xlsxwriter.Workbook(buffer, {'in_memory': True})
        title = book.add_format({'bold': True, 'font_size': 14})
        head = book.add_format({'bold': True, 'bg_color': '#714B67', 'font_color': '#FFFFFF', 'border': 1})
        money = book.add_format({'num_format': '#,##0.00', 'border': 1})
        number = book.add_format({'num_format': '#,##0.00', 'border': 1})
        text = book.add_format({'border': 1})
        bold_money = book.add_format({'num_format': '#,##0.00', 'bold': True, 'top': 2})
        sheet = book.add_worksheet(data['title'][:31])
        sheet.write(0, 0, f"{data['title']} — {data['company']}", title)
        sheet.write(1, 0, self.env._('Printed on %s', data['date'].strftime('%Y-%m-%d %H:%M')))
        row = 3
        if self.report_type == 'summary':
            headers = [self.env._('Warehouse'), self.env._('Code'), self.env._('Products'), self.env._('Quantity'),
                       self.env._('Value'), self.env._('Share %')]
            sheet.write_row(row, 0, headers, head)
            for line in data['summary']:
                row += 1
                sheet.write(row, 0, line['name'], text)
                sheet.write(row, 1, line['code'], text)
                sheet.write(row, 2, line['products'], text)
                sheet.write(row, 3, line['quantity'], number)
                sheet.write(row, 4, line['value'], money)
                sheet.write(row, 5, line['share'], number)
            sheet.write(row + 1, 4, data['total_value'], bold_money)
            sheet.set_column(0, 0, 28)
            sheet.set_column(1, 5, 14)
        elif self.report_type == 'detailed':
            headers = [self.env._('Warehouse'), self.env._('Reference'), self.env._('Product'), self.env._('Category'),
                       self.env._('Quantity'), self.env._('Unit'), self.env._('Average Cost'),
                       self.env._('Company Cost'), self.env._('Gap %'), self.env._('Value')]
            sheet.write_row(row, 0, headers, head)
            for line in data['detailed']:
                row += 1
                sheet.write_row(row, 0, [line['warehouse'], line['code'], line['product'], line['category']], text)
                sheet.write(row, 4, line['quantity'], number)
                sheet.write(row, 5, line['uom'], text)
                sheet.write(row, 6, line['avg_cost'], money)
                sheet.write(row, 7, line['company_cost'], money)
                sheet.write(row, 8, line['gap'], number)
                sheet.write(row, 9, line['value'], money)
            sheet.write(row + 1, 9, data['total_value'], bold_money)
            sheet.set_column(0, 0, 22)
            sheet.set_column(1, 3, 26)
            sheet.set_column(4, 9, 13)
            sheet.autofilter(3, 0, max(row, 4), 9)
        else:
            headers = [self.env._('Reference'), self.env._('Product')] + [c['code'] for c in data['columns']] + [
                self.env._('Company Cost'), self.env._('Lowest'), self.env._('Highest'), self.env._('Spread %')]
            sheet.write_row(row, 0, headers, head)
            for line in data['comparison']:
                row += 1
                sheet.write(row, 0, line['code'], text)
                sheet.write(row, 1, line['product'], text)
                col = 2
                for cost in line['costs']:
                    sheet.write(row, col, cost if cost is not None else '', money)
                    col += 1
                for key in ('company_cost', 'low', 'high', 'spread'):
                    sheet.write(row, col, line[key], money if key != 'spread' else number)
                    col += 1
            sheet.set_column(0, 0, 14)
            sheet.set_column(1, 1, 30)
            sheet.set_column(2, 2 + len(data['columns']) + 3, 12)
        sheet.freeze_panes(4, 0)
        book.close()
        name = f'warehouse_valuation_{self.report_type}.xlsx'
        self.write({'xlsx_file': base64.b64encode(buffer.getvalue()).decode(), 'xlsx_name': name})
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': f'/web/content/stock.warehouse.valuation.report/{self.id}/xlsx_file/{name}?download=true'}
