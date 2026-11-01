from odoo import fields, models

EMAIL_MODES = [
    ('private_first', 'Private e-mail, else work e-mail'),
    ('private', 'Private e-mail'),
    ('work', 'Work e-mail'),
    ('both', 'Private and work e-mail'),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    payslip_email_mode = fields.Selection(EMAIL_MODES, 'Send payslips to', default='private_first', required=True)
    payslip_pdf_password = fields.Selection([
        ('none', 'No password'),
        ('birthday', "Employee's date of birth (DDMMYYYY)"),
    ], 'Protect payslip PDFs', default='none', required=True)
