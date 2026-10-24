import base64
import io

import openpyxl

from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user, tagged

HEADER = 'Product,Reference,BoM Quantity,BoM Type,Component,Component Quantity,Component UoM,Operation,Work Center,Duration (min)'


@tagged('post_install', '-at_install')
class TestBomImport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Product = cls.env['product.product']
        cls.table = Product.create({'name': 'Dining Table', 'default_code': 'TABLE', 'barcode': '5400000000001'})
        cls.desk_kit = Product.create({'name': 'Desk Kit', 'default_code': 'DESKKIT'})
        cls.leg = Product.create({'name': 'Table Leg', 'default_code': 'LEG', 'barcode': '5400000000002', 'is_storable': True})
        cls.top = Product.create({'name': 'Table Top', 'default_code': 'TOP', 'barcode': '5400000000003', 'is_storable': True})
        cls.screw = Product.create({'name': 'Screw', 'default_code': 'SCREW', 'is_storable': True})
        cls.dozen = cls.env.ref('uom.product_uom_dozen')
        cls.dozen.active = True

    def wizard(self, content, filename='boms.csv', **values):
        if isinstance(content, str):
            content = content.encode()
        return self.env['mrp.bom.import.wizard'].create(dict({
            'file': base64.b64encode(content).decode(), 'filename': filename}, **values))

    def boms(self, product):
        return self.env['mrp.bom'].search([('product_tmpl_id', '=', product.product_tmpl_id.id)])

    def test_csv_creates_grouped_boms_with_operations(self):
        csv_data = '\n'.join([
            HEADER,
            'TABLE,T-V1,1,normal,LEG,4,Units,Assembly,Assembly line,30',
            'TABLE,T-V1,1,normal,TOP,1,,Assembly,Assembly line,30',
            f'TABLE,T-V1,1,normal,SCREW,2,{self.dozen.name},Assembly,Assembly line,30',
            'DESKKIT,,1,kit,TOP,1,,,,',
        ])
        wizard = self.wizard(csv_data)
        wizard.action_import()
        self.assertEqual((wizard.created_count, wizard.error_count), (2, 0))
        bom = self.boms(self.table)
        self.assertEqual(bom.code, 'T-V1')
        self.assertEqual(bom.type, 'normal')
        self.assertEqual(len(bom.bom_line_ids), 3)
        screw_line = bom.bom_line_ids.filtered(lambda l: l.product_id == self.screw)
        uom_field = 'uom_id' if 'uom_id' in screw_line._fields else 'product_uom_id'
        self.assertEqual((screw_line.product_qty, screw_line[uom_field]), (2, self.dozen))
        self.assertEqual(bom.operation_ids.name, 'Assembly')
        self.assertEqual(bom.operation_ids.workcenter_id.name, 'Assembly line')
        self.assertEqual(bom.operation_ids.time_cycle_manual, 30)
        self.assertEqual(set(bom.bom_line_ids.operation_id.ids), set(bom.operation_ids.ids))
        self.assertEqual(self.boms(self.desk_kit).type, 'phantom')
        self.assertEqual(wizard.result_line_ids.mapped('level'), ['created', 'created'])

    def test_semicolon_and_barcode_matching(self):
        csv_data = 'Product;Component;Component Quantity\n5400000000001;5400000000002;4\n5400000000001;5400000000003;1\n'
        wizard = self.wizard(csv_data, product_match='barcode')
        wizard.action_import()
        self.assertEqual(wizard.created_count, 1)
        self.assertEqual(self.boms(self.table).bom_line_ids.product_id, self.leg | self.top)

    def test_match_by_name(self):
        wizard = self.wizard('Product,Component,Component Quantity\nDining Table,Table Leg,4\n', product_match='name')
        wizard.action_import()
        self.assertEqual(self.boms(self.table).bom_line_ids.product_id, self.leg)

    def test_xlsx(self):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(['Product', 'Component', 'Component Quantity', 'BoM Quantity'])
        sheet.append([5400000000001, 5400000000002, 4.0, 2.0])
        buffer = io.BytesIO()
        workbook.save(buffer)
        # barcodes typed as numbers in Excel still match
        wizard = self.wizard(buffer.getvalue(), filename='boms.xlsx', product_match='barcode')
        wizard.action_import()
        self.assertEqual(wizard.error_count, 0, wizard.result_line_ids.mapped('message'))
        bom = self.boms(self.table)
        self.assertEqual((bom.product_qty, bom.bom_line_ids.product_qty), (2, 4))

    def test_errors_are_reported_per_row(self):
        csv_data = '\n'.join([
            'Product,Component,Component Quantity',
            'TABLE,LEG,4',
            'TABLE,UNKNOWN,1',
            'DESKKIT,TOP,abc',
            'NOPE,TOP,1',
            'TOP,TOP,1',
        ])
        wizard = self.wizard(csv_data)
        wizard.action_import()
        self.assertEqual((wizard.created_count, wizard.error_count), (0, 4))
        errors = {r.row: r.message for r in wizard.result_line_ids}
        self.assertIn('UNKNOWN', errors[3])
        self.assertIn('not a number', errors[4])
        self.assertIn('NOPE', errors[5])
        self.assertIn('own component', errors[6])
        self.assertFalse(self.boms(self.table))

    def test_skip_errors_imports_valid_boms(self):
        csv_data = 'Product,Component,Component Quantity\nTABLE,LEG,4\nDESKKIT,UNKNOWN,1\n'
        wizard = self.wizard(csv_data)
        wizard.action_import()
        self.assertEqual((wizard.created_count, wizard.error_count), (1, 1))
        self.assertTrue(self.boms(self.table))

    def test_stop_on_error_imports_nothing(self):
        csv_data = 'Product,Component,Component Quantity\nTABLE,LEG,4\nDESKKIT,UNKNOWN,1\n'
        wizard = self.wizard(csv_data, on_error='stop')
        wizard.action_import()
        self.assertEqual(wizard.created_count, 0)
        self.assertFalse(self.boms(self.table))

    def test_create_missing_components(self):
        wizard = self.wizard('Product,Component,Component Quantity\nTABLE,GLUE-01,0.5\n', create_missing_components=True)
        wizard.action_import()
        glue = self.env['product.product'].search([('default_code', '=', 'GLUE-01')])
        self.assertTrue(glue.is_storable)
        self.assertEqual(self.boms(self.table).bom_line_ids.product_id, glue)

    def test_update_and_skip_modes(self):
        self.wizard('Product,Reference,Component,Component Quantity\nTABLE,V1,LEG,4\n').action_import()
        bom = self.boms(self.table)
        self.wizard('Product,Reference,Component,Component Quantity\nTABLE,V1,TOP,1\nTABLE,V1,SCREW,8\n',
                    import_mode='update').action_import()
        self.assertEqual(self.boms(self.table), bom, "same BoM updated")
        self.assertEqual(bom.bom_line_ids.product_id, self.top | self.screw)
        wizard = self.wizard('Product,Reference,Component,Component Quantity\nTABLE,V1,LEG,99\n', import_mode='skip')
        wizard.action_import()
        self.assertEqual(wizard.skipped_count, 1)
        self.assertEqual(bom.bom_line_ids.product_id, self.top | self.screw)
        self.wizard('Product,Reference,Component,Component Quantity\nTABLE,V1,LEG,1\n', import_mode='create').action_import()
        self.assertEqual(len(self.boms(self.table)), 2)

    def test_csv_from_excel_windows_1252(self):
        # French Excel saves CSV in Windows-1252: accents must survive (they were replaced by U+FFFD)
        chair = self.env['product.product'].create({'name': 'Chaise pliée'})
        foot = self.env['product.product'].create({'name': 'Pièce métal', 'is_storable': True})
        content = 'Product;Component;Component Quantity\nChaise pliée;Pièce métal;4\n'.encode('cp1252')
        wizard = self.wizard(content, product_match='name')
        wizard.action_import()
        self.assertEqual((wizard.created_count, wizard.error_count), (1, 0))
        self.assertEqual(self.boms(chair).bom_line_ids.product_id, foot)
        # UTF-8 with BOM still works
        wizard = self.wizard('\ufeffProduct,Component,Component Quantity\nDining Table,Table Leg,4\n'.encode(),
                             product_match='name')
        wizard.action_import()
        self.assertEqual(wizard.created_count, 1)

    def test_damaged_xlsx(self):
        with self.assertRaisesRegex(UserError, 'cannot be read as an Excel'):
            self.wizard(b'this is not a zip file', filename='boms.xlsx').action_import()

    def test_bad_header(self):
        with self.assertRaises(UserError):
            self.wizard('Item,Qty\nTABLE,1\n').action_import()
        with self.assertRaises(UserError):
            self.wizard(b'x', filename='boms.pdf').action_import()

    def test_samples(self):
        for method in ('action_download_sample_csv', 'action_download_sample_xlsx'):
            action = getattr(self.env['mrp.bom.import.wizard'], method)()
            attachment = self.env['ir.attachment'].browse(int(action['url'].split('/')[3].split('?')[0]))
            self.assertTrue(attachment.file_size)
        # the sample file itself imports (once its products exist)
        Product = self.env['product.product']
        for code in ('FURN_8888', 'FURN_9999', 'FURN_0001', 'FURN_0002', 'FURN_0003', 'FURN_0004'):
            Product.create({'name': code, 'default_code': code})
        xlsx = self.env['ir.attachment'].search([('name', '=', 'bom_import_sample.xlsx')], limit=1)
        wizard = self.wizard(bytes(xlsx.raw), filename='sample.xlsx')
        wizard.action_import()
        self.assertEqual((wizard.created_count, wizard.error_count), (2, 0))

    def test_access(self):
        user = new_test_user(self.env, 'mrp_only', groups='mrp.group_mrp_user')
        with self.assertRaises(AccessError):
            self.env['mrp.bom.import.wizard'].with_user(user).create({'file': base64.b64encode(b'x').decode()})
        manager = new_test_user(self.env, 'mrp_boss', groups='mrp.group_mrp_manager')
        self.assertTrue(manager.has_group('mrp_bom_import.group_mrp_bom_import'))
