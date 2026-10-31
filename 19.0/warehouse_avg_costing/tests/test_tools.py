import base64
import io

import openpyxl

from odoo.tests import HttpCase, tagged

from .common import WarehouseCostCommon


@tagged('post_install', '-at_install')
class TestWarehouseCostTools(WarehouseCostCommon):

    def setUp(self):
        super().setUp()
        self.receive(self.wh1, 100, 10.0)
        self.receive(self.wh2, 50, 14.0)
        self.deliver(self.wh2, 10)

    def test_valuation_report(self):
        Report = self.env['stock.warehouse.valuation.report']
        summary = Report.create({'report_type': 'summary'})._report_data()
        by_code = {line['code']: line for line in summary['summary']}
        self.assertEqual(by_code[self.wh2.code]['value'], 560.0)
        self.assertAlmostEqual(summary['total_value'], 1560.0)
        self.assertAlmostEqual(by_code[self.wh1.code]['share'], 64.1)
        detailed = Report.create({'report_type': 'detailed', 'warehouse_ids': [(6, 0, self.wh2.ids)]})._report_data()
        self.assertEqual([(l['warehouse'], l['quantity'], l['avg_cost']) for l in detailed['detailed']],
                         [('North Depot', 40, 14.0)])
        comparison = Report.create({'report_type': 'comparison'})._report_data()
        line = comparison['comparison'][0]
        self.assertEqual((line['low'], line['high'], line['spread']), (10.0, 14.0, 40.0))
        for report_type in ('summary', 'detailed', 'comparison'):
            wizard = Report.create({'report_type': report_type})
            action = wizard.action_xlsx()
            self.assertIn('/web/content/stock.warehouse.valuation.report/', action['url'])
            self.assertEqual(base64.b64decode(wizard.xlsx_file)[:2], b'PK')
            html = self.env['ir.actions.report']._render_qweb_html(
                'warehouse_avg_costing.report_warehouse_valuation', wizard.ids)[0].decode()
            self.assertIn('Total value', html)
        action = Report.create({'report_type': 'comparison'}).action_view()
        self.assertEqual(action['context']['pivot_column_groupby'], ['warehouse_id'])

    def test_cost_matrix_round_trip(self):
        Matrix = self.env['stock.warehouse.cost.matrix']
        export = Matrix.create({'mode': 'export', 'warehouse_ids': [(6, 0, (self.wh1 | self.wh2).ids)]})
        export.action_export()
        book = openpyxl.load_workbook(io.BytesIO(base64.b64decode(export.file)))
        sheet = book.worksheets[0]
        header = [cell.value for cell in sheet[1]]
        self.assertEqual(header[:3], ['ID', 'Reference', 'Product'])
        product_row = next(r for r in sheet.iter_rows(min_row=2) if r[0].value == self.product.id)
        col = header.index(self.wh2.code)
        self.assertEqual(product_row[col].value, 14.0)
        product_row[col].value = 15.5
        product_row[header.index('XX') if 'XX' in header else 0].value = self.product.id
        buffer = io.BytesIO()
        book.save(buffer)
        importer = Matrix.create({'mode': 'import', 'file': base64.b64encode(buffer.getvalue()).decode(),
                                  'reason': 'Q3 price review'})
        importer.action_import()
        self.assertEqual(len(importer.adjustment_ids), 1)
        self.assertEqual(importer.adjustment_ids.state, 'done')
        self.assertEqual(self.row(self.wh2).avg_cost, 15.5)
        self.assertIn('1 unchanged', importer.result)

    def test_dashboard(self):
        data = self.env['stock.warehouse.cost.dashboard'].get_data()
        self.assertAlmostEqual(data['kpis']['value'], 1560.0)
        self.assertEqual(data['kpis']['warehouses'], 2)
        self.assertEqual(data['spreads'][0]['spread'], 40.0)
        self.assertEqual(data['recent'][0]['kind_key'], 'out')
        self.assertEqual(data['warehouses'][0]['code'], self.wh1.code)

    def test_product_views(self):
        template = self.product.product_tmpl_id
        self.assertTrue(template.warehouse_costing_active)
        self.assertEqual(len(template.warehouse_cost_ids), 2)
        action = template.action_view_cost_history()
        self.assertEqual(action['res_model'], 'stock.warehouse.cost.line')
        self.assertEqual(self.row(self.wh2).cost_gap, round((14.0 - self.product.standard_price)
                                                           / self.product.standard_price * 100, 1))


@tagged('post_install', '-at_install')
class TestWarehouseCostTour(HttpCase):

    def test_dashboard_tour(self):
        self.env.company.warehouse_costing = True
        self.start_tour('/odoo/warehouse-costing', 'warehouse_avg_costing_tour', login='admin')
