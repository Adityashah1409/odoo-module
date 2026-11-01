import base64
import io
import zipfile
from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, new_test_user
from odoo.tools.pdf import PdfFileReader, PdfFileWriter


def make_pdf():
    writer = PdfFileWriter()
    writer.add_blank_page(200, 200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class TestPayslip(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'email': 'hr@example.com', 'payslip_email_mode': 'private_first',
                           'payslip_pdf_password': 'none'})
        cls.officer = new_test_user(cls.env, 'pay_officer', groups='payslip_send_email.group_payslip_officer')
        cls.lotte_user = new_test_user(cls.env, 'lotte', groups='base.group_user')
        Employee = cls.env['hr.employee']
        cls.lotte = Employee.create({'name': 'Lotte Janssens', 'barcode': 'EMP042', 'user_id': cls.lotte_user.id,
                                     'private_email': 'lotte@home.example.com', 'work_email': 'lotte@example.com',
                                     'birthday': date(1990, 3, 5)})
        cls.jan = Employee.create({'name': 'Jan De Vries', 'work_email': 'jan@example.com'})
        cls.peeters = Employee.create({'name': 'Jan Peeters', 'private_email': 'peeters@home.example.com'})
        cls.jerome = Employee.create({'name': 'Jérôme Müller'})
        cls.batch = cls.env['hr.payslip.document.batch'].create({
            'date_from': date(2026, 10, 1), 'date_to': date(2026, 10, 31)})
        cls.pdf = make_pdf()

    def _doc(self, employee, **vals):
        return self.env['hr.payslip.document'].create(dict({
            'employee_id': employee.id, 'batch_id': self.batch.id, 'date_from': self.batch.date_from,
            'date_to': self.batch.date_to, 'pdf_file': base64.b64encode(self.pdf),
            'pdf_filename': f'{employee.name}.pdf',
        }, **vals))

    def test_names(self):
        self.assertEqual(self.batch.name, 'Payslips October 2026')
        self.assertEqual(self._doc(self.lotte).name, 'Payslip October 2026 - Lotte Janssens')

    def test_match_employee(self):
        Doc = self.env['hr.payslip.document']
        employees = self.lotte | self.jan | self.peeters | self.jerome
        self.assertEqual(Doc._match_employee('2026-10_Janssens_Lotte.pdf', employees), self.lotte)
        self.assertEqual(Doc._match_employee('payslip EMP042.pdf', employees), self.lotte, 'badge ID')
        self.assertEqual(Doc._match_employee('De Vries Jan 10-2026.pdf', employees), self.jan)
        self.assertEqual(Doc._match_employee('jerome_muller.pdf', employees), self.jerome, 'accents')
        self.assertEqual(Doc._match_employee('2026-10_DeVries_Jan.pdf', employees), self.jan, 'glued words')
        self.assertFalse(Doc._match_employee('jan.pdf', employees))
        self.assertFalse(Doc._match_employee('Peeters.pdf', employees), 'all name words are needed')

    def test_import_wizard(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as zf:
            zf.writestr('october/De_Vries_Jan.pdf', self.pdf)
            zf.writestr('october/readme.txt', 'not a payslip')
        Attachment = self.env['ir.attachment'].with_user(self.officer)  # uploaded by the officer
        files = Attachment.create([
            {'name': 'Janssens Lotte.pdf', 'datas': base64.b64encode(self.pdf)},
            {'name': 'EMP042-duplicate.pdf', 'datas': base64.b64encode(self.pdf)},
            {'name': 'unknown person.pdf', 'datas': base64.b64encode(self.pdf)},
            {'name': 'payslips.zip', 'datas': base64.b64encode(archive.getvalue())},
        ])
        wizard = self.env['hr.payslip.import.wizard'].with_user(self.officer).create({
            'batch_id': self.batch.id, 'attachment_ids': [(6, 0, files.ids)]})
        action = wizard.action_import()
        docs = self.batch.document_ids
        self.assertEqual(len(docs), 4)
        self.assertEqual(docs.employee_id, self.lotte | self.jan)
        self.assertEqual(self.batch.count_unassigned, 2, 'unknown file and second file for Lotte')
        self.assertEqual(action['res_model'], 'hr.payslip.document', 'open the list to assign by hand')
        self.assertTrue(all(d.date_from == date(2026, 10, 1) for d in docs))
        with self.assertRaises(UserError):
            self.env['hr.payslip.import.wizard'].create({'batch_id': self.batch.id}).action_import()

    def test_recipients(self):
        self.assertEqual(self.lotte._payslip_email_addresses(), ['lotte@home.example.com'])
        self.assertEqual(self.jan._payslip_email_addresses(), ['jan@example.com'], 'no private e-mail: work')
        self.company.payslip_email_mode = 'both'
        self.assertEqual(self.lotte._payslip_email_addresses(), ['lotte@home.example.com', 'lotte@example.com'])
        self.company.payslip_email_mode = 'private'
        self.assertEqual(self.jan._payslip_email_addresses(), [])
        self.lotte.payslip_email_mode = 'work'
        self.assertEqual(self.lotte._payslip_email_addresses(), ['lotte@example.com'], 'employee choice wins')
        self.lotte.payslip_email_mode = 'none'
        self.assertEqual(self.lotte._payslip_email_addresses(), [])

    def test_send(self):
        lotte, jan, jerome = self._doc(self.lotte), self._doc(self.jan), self._doc(self.jerome)
        no_employee = self._doc(self.lotte, employee_id=False)
        self.batch.with_user(self.officer).action_send_all()
        self.assertEqual(lotte.state, 'sent')
        self.assertEqual(lotte.sent_to, 'lotte@home.example.com')
        self.assertEqual(jan.state, 'sent')
        self.assertEqual(jerome.state, 'error')
        self.assertIn('No e-mail address', jerome.error_message)
        self.assertEqual(no_employee.state, 'error')
        mail = self.env['mail.mail'].search([('model', '=', 'hr.payslip.document'), ('res_id', '=', lotte.id)])
        self.assertEqual(mail.email_to, 'lotte@home.example.com')
        self.assertFalse(mail.recipient_ids, 'only the employee, no followers')
        self.assertEqual(len(mail.attachment_ids), 1)
        self.assertIn('October 2026', mail.subject)
        self.assertNotIn('DDMMYYYY', mail.body_html)
        self.assertEqual(self.batch.state, 'draft', 'errors left')
        jerome.employee_id.private_email = 'jerome@home.example.com'
        no_employee.employee_id = self.peeters
        self.batch.action_send_all()
        self.assertEqual(self.batch.state, 'done')
        self.assertEqual(self.batch.count_sent, 4)

    def test_password_protection(self):
        self.company.payslip_pdf_password = 'birthday'
        lotte, jan = self._doc(self.lotte), self._doc(self.jan)
        (lotte | jan).action_send()
        self.assertEqual(jan.state, 'error', 'no date of birth')
        mail = self.env['mail.mail'].search([('model', '=', 'hr.payslip.document'), ('res_id', '=', lotte.id)])
        self.assertIn('DDMMYYYY', mail.body_html)
        reader = PdfFileReader(io.BytesIO(base64.b64decode(mail.attachment_ids.datas)), strict=False)
        self.assertTrue(reader.is_encrypted)
        self.assertTrue(reader.decrypt('05031990'))
        self.assertFalse(PdfFileReader(io.BytesIO(base64.b64decode(lotte.pdf_file)), strict=False).is_encrypted,
                         'the stored payslip stays readable for HR')

    def test_schedule(self):
        self._doc(self.lotte)
        with self.assertRaises(UserError):
            self.batch.action_schedule()
        self.batch.scheduled_date = fields.Datetime.now() + timedelta(hours=1)
        self.batch.action_schedule()
        self.env['hr.payslip.document.batch']._cron_send_scheduled()
        self.assertEqual(self.batch.state, 'scheduled', 'not yet')
        self.batch.scheduled_date = fields.Datetime.now() - timedelta(minutes=1)
        self.env['hr.payslip.document.batch']._cron_send_scheduled()
        self.assertEqual(self.batch.state, 'done')
        self.assertEqual(self.batch.document_ids.state, 'sent')

    def test_employee_access(self):
        mine, other = self._doc(self.lotte), self._doc(self.jan)
        Doc = self.env['hr.payslip.document'].with_user(self.lotte_user)
        self.assertFalse(Doc.search([]), 'nothing before it is sent')
        (mine | other).action_send()
        self.assertEqual(Doc.search([]), mine)
        action = self.env['ir.actions.act_window']._for_xml_id('payslip_send_email.action_my_payslips')
        self.assertTrue(action['domain'])
        with self.assertRaises(AccessError):
            mine.with_user(self.lotte_user).write({'note': 'x'})
        with self.assertRaises(AccessError):
            other.with_user(self.lotte_user).read(['name'])
        with self.assertRaises(AccessError):
            self.env['hr.payslip.document.batch'].with_user(self.lotte_user).search([])
        self.assertIn('/web/content/hr.payslip.document/', mine.with_user(self.lotte_user).action_download()['url'])
