from odoo import fields, models


class MailMessage(models.Model):
    _inherit = 'mail.message'

    pinned_by_id = fields.Many2one('res.users', 'Pinned by', readonly=True, copy=False)
