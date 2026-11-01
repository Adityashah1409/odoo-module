from odoo import fields, models

from .res_users import ORDERS


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatter_default_order = fields.Selection(ORDERS, 'Default chatter order', default='desc',
                                             config_parameter='chatter_sort_by_date.default_order')
