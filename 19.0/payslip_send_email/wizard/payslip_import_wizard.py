import base64
import io
import os
import zipfile

from odoo import fields, models
from odoo.exceptions import UserError


class PayslipImportWizard(models.TransientModel):
    _name = 'hr.payslip.import.wizard'
    _description = 'Import payslip PDFs'

    batch_id = fields.Many2one('hr.payslip.document.batch', required=True)
    attachment_ids = fields.Many2many('ir.attachment', string='PDF files or ZIP archives')

    def _pdf_files(self):
        """ (file name, bytes) of every PDF, also inside ZIP archives. """
        files = []
        for attachment in self.attachment_ids:
            data = base64.b64decode(attachment.datas or b'')
            name = attachment.name or ''
            if name.lower().endswith('.zip') or data[:2] == b'PK':
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for info in archive.infolist():
                        if not info.is_dir() and info.filename.lower().endswith('.pdf'):
                            files.append((os.path.basename(info.filename), archive.read(info)))
            elif name.lower().endswith('.pdf') or data[:4] == b'%PDF':
                files.append((name, data))
        return files

    def action_import(self):
        self.ensure_one()
        batch = self.batch_id
        files = self._pdf_files()
        if not files:
            raise UserError(self.env._('Add PDF files (or ZIP archives of PDF files).'))
        Document = self.env['hr.payslip.document']
        employees = self.env['hr.employee'].search([('company_id', 'in', [batch.company_id.id, False])])
        already = batch.document_ids.filtered(lambda d: d.state != 'cancel').employee_id
        vals_list = []
        for filename, data in files:
            employee = Document._match_employee(filename, employees)
            if employee and employee in already:
                employee = self.env['hr.employee']  # second file for the same person: let HR decide
            already |= employee
            vals_list.append({
                'batch_id': batch.id,
                'company_id': batch.company_id.id,
                'employee_id': employee.id,
                'date_from': batch.date_from,
                'date_to': batch.date_to,
                'pdf_file': base64.b64encode(data),
                'pdf_filename': filename,
            })
        documents = Document.create(vals_list)
        unmatched = documents.filtered(lambda d: not d.employee_id)
        batch.message_post(body=self.env._(
            '%(count)s payslip(s) imported, %(unmatched)s without employee.',
            count=len(documents), unmatched=len(unmatched)))
        self.attachment_ids.unlink()
        return batch.action_view_documents() if unmatched else {'type': 'ir.actions.act_window_close'}
