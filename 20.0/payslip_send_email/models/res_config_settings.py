from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    payslip_email_mode = fields.Selection(related='company_id.payslip_email_mode', readonly=False)
    payslip_pdf_password = fields.Selection(related='company_id.payslip_pdf_password', readonly=False)
