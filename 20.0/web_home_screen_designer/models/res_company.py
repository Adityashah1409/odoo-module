from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    home_screen_allow_user_layout = fields.Boolean(
        'Users can save their own home screen', default=True,
        help='When off, everybody sees the company home screen and only administrators can change it.')
