from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mail_default_cc = fields.Char(related='company_id.mail_default_cc', readonly=False)
    mail_default_bcc = fields.Char(related='company_id.mail_default_bcc', readonly=False)
    mail_default_reply_to = fields.Char(related='company_id.mail_default_reply_to', readonly=False)
