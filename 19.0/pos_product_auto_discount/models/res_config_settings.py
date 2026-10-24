from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_auto_discount_enabled = fields.Boolean(related='pos_config_id.auto_discount_enabled', readonly=False)
    pos_auto_discount_badge = fields.Boolean(related='pos_config_id.auto_discount_badge', readonly=False)

    def action_pos_auto_discounts(self):
        return self.pos_config_id.action_open_auto_discounts()
