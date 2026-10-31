import base64
import io

import openpyxl
import xlsxwriter

from odoo import fields, models
from odoo.exceptions import UserError


class StockWarehouseCostMatrix(models.TransientModel):
    """Export the average cost of every product in every warehouse to Excel, and import it back as adjustments."""
    _name = 'stock.warehouse.cost.matrix'
    _description = 'Warehouse cost matrix (Excel)'

    mode = fields.Selection([('export', 'Export'), ('import', 'Import')], default='export', required=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    warehouse_ids = fields.Many2many('stock.warehouse', string='Warehouses', domain="[('company_id', '=', company_id)]",
                                     help='Empty: all warehouses.')
    categ_ids = fields.Many2many('product.category', string='Product Categories', help='Empty: all categories.')
    file = fields.Binary('Excel file', attachment=False)
    file_name = fields.Char()
    reason = fields.Char(default=lambda self: self.env._('Cost matrix import'))
    result = fields.Text(readonly=True)
    adjustment_ids = fields.Many2many('stock.warehouse.cost.adjustment', readonly=True)

    def _warehouses(self):
        return self.warehouse_ids or self.env['stock.warehouse'].search([('company_id', '=', self.company_id.id)])

    def _products(self):
        domain = [('is_storable', '=', True)]
        if self.categ_ids:
            domain.append(('categ_id', 'child_of', self.categ_ids.ids))
        products = self.env['product.product'].search(domain, order='default_code, name')
        return self.env['stock.warehouse.cost']._applicable_products(products, self.company_id)

    def action_export(self):
        self.ensure_one()
        warehouses = self._warehouses()
        products = self._products()
        rows = self.env['stock.warehouse.cost'].search([('company_id', '=', self.company_id.id),
                                                        ('product_id', 'in', products.ids)])
        by_key = {(r.product_id.id, r.warehouse_id.id): r for r in rows}
        buffer = io.BytesIO()
        book = xlsxwriter.Workbook(buffer, {'in_memory': True})
        head = book.add_format({'bold': True, 'bg_color': '#714B67', 'font_color': '#FFFFFF'})
        locked = book.add_format({'bg_color': '#F2F2F2'})
        price = book.add_format({'num_format': '0.00##', 'bg_color': '#FFF8E1'})
        for sheet_name, field in ((self.env._('Average cost'), 'avg_cost'), (self.env._('Quantity'), 'quantity'),
                                  (self.env._('Value'), 'value')):
            sheet = book.add_worksheet(sheet_name)
            sheet.write_row(0, 0, ['ID', self.env._('Reference'), self.env._('Product')] +
                            [w.code for w in warehouses], head)
            for index, product in enumerate(products, start=1):
                sheet.write(index, 0, product.id, locked)
                sheet.write(index, 1, product.default_code or '', locked)
                sheet.write(index, 2, product.display_name, locked)
                for col, warehouse in enumerate(warehouses, start=3):
                    row = by_key.get((product.id, warehouse.id))
                    value = row[field] if row else (product.with_company(self.company_id).standard_price
                                                    if field == 'avg_cost' else 0.0)
                    sheet.write(index, col, value, price if field == 'avg_cost' else None)
            sheet.set_column(0, 0, 7)
            sheet.set_column(1, 1, 14)
            sheet.set_column(2, 2, 34)
            sheet.set_column(3, 3 + len(warehouses), 12)
            sheet.freeze_panes(1, 3)
        book.close()
        self.write({'file': base64.b64encode(buffer.getvalue()).decode(), 'file_name': 'warehouse_cost_matrix.xlsx',
                    'result': self.env._('%(products)s products × %(warehouses)s warehouses exported. Change the '
                                         'yellow cells of the first sheet and import the file back.',
                                         products=len(products), warehouses=len(warehouses))})
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': f'/web/content/stock.warehouse.cost.matrix/{self.id}/file/warehouse_cost_matrix.xlsx'
                       '?download=true'}

    def _read_file(self):
        if not self.file:
            raise UserError(self.env._('Choose the Excel file exported by this wizard.'))
        content = self.file if isinstance(self.file, (bytes, bytearray)) else self.file.encode()
        try:
            book = openpyxl.load_workbook(io.BytesIO(base64.b64decode(content)), read_only=True, data_only=True)
        except Exception as exc:
            raise UserError(self.env._('This is not a valid Excel (.xlsx) file: %s', exc)) from exc
        rows = list(book.worksheets[0].iter_rows(values_only=True))
        if not rows or not rows[0] or rows[0][0] != 'ID':
            raise UserError(self.env._('The first sheet must start with the columns ID, Reference, Product.'))
        return rows

    def action_import(self):
        self.ensure_one()
        rows = self._read_file()
        header = rows[0]
        Warehouse = self.env['stock.warehouse']
        warehouses = {}
        for col, code in enumerate(header[3:], start=3):
            warehouse = Warehouse.search([('code', '=', code), ('company_id', '=', self.company_id.id)], limit=1)
            if warehouse:
                warehouses[col] = warehouse
        Cost = self.env['stock.warehouse.cost']
        Product = self.env['product.product']
        applicable = Cost._applicable_products
        created = self.env['stock.warehouse.cost.adjustment']
        skipped, errors = 0, []
        for line_no, values in enumerate(rows[1:], start=2):
            if not values or values[0] in (None, ''):
                continue
            product = Product.browse(int(values[0])).exists()
            if not product or not applicable(product, self.company_id):
                errors.append(self.env._('Row %(row)s: product %(id)s not valued per warehouse', row=line_no,
                                         id=values[0]))
                continue
            for col, warehouse in warehouses.items():
                cell = values[col] if col < len(values) else None
                if cell in (None, ''):
                    continue
                try:
                    new_cost = float(cell)
                except (TypeError, ValueError):
                    errors.append(self.env._('Row %(row)s, %(wh)s: "%(cell)s" is not a number', row=line_no,
                                             wh=warehouse.code, cell=cell))
                    continue
                row = Cost.search([('product_id', '=', product.id), ('warehouse_id', '=', warehouse.id),
                                   ('company_id', '=', self.company_id.id)], limit=1)
                current = row.avg_cost if row else product.with_company(self.company_id).standard_price
                if self.company_id.currency_id.compare_amounts(current, new_cost) == 0:
                    skipped += 1
                    continue
                created |= created.create({'product_id': product.id, 'warehouse_id': warehouse.id,
                                           'company_id': self.company_id.id, 'new_cost': new_cost,
                                           'reason': self.reason})
        created.action_submit()
        applied = created.filtered(lambda a: a.state == 'done')
        lines = [self.env._('%s cost change(s) found.', len(created)),
                 self.env._('%s applied, %s waiting for approval, %s unchanged.', len(applied),
                            len(created) - len(applied), skipped)]
        lines += errors
        self.write({'result': '\n'.join(lines), 'adjustment_ids': [(6, 0, created.ids)]})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'views': [(False, 'form')], 'target': 'new', 'name': self.env._('Import warehouse costs')}

    def action_open_adjustments(self):
        action = self.env['ir.actions.act_window']._for_xml_id(
            'warehouse_avg_costing.action_stock_warehouse_cost_adjustment')
        action['domain'] = [('id', 'in', self.adjustment_ids.ids)]
        return action
