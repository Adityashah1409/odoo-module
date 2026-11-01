from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    chatter_pin_access = fields.Selection([
        ('write', 'Users who can edit the record'),
        ('read', 'Everyone who can see the record'),
    ], string='Who can pin', default='write', config_parameter='chatter_pin_message.access')
    chatter_pin_max = fields.Integer('Pins per record', default=5, config_parameter='chatter_pin_message.max',
                                     help='0 = no limit.')
