from odoo import api, fields, models

from .res_users import POSITIONS


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    flexible_chatter_position = fields.Selection(POSITIONS, 'Default chatter position', default='auto',
                                                 config_parameter='flexible_chatter.position')
    flexible_chatter_width = fields.Integer('Default chatter width (%)',
                                            config_parameter='flexible_chatter.width')

    @api.onchange('flexible_chatter_width')
    def _onchange_flexible_chatter_width(self):
        self.flexible_chatter_width = self.env['res.users']._flexible_chatter_width(self.flexible_chatter_width)
