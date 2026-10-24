from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_shortcut_enabled = fields.Boolean(related='pos_config_id.shortcut_enabled', readonly=False)

    def action_pos_shortcuts(self):
        self.ensure_one()
        if self.pos_config_id.shortcut_enabled and not self.pos_config_id.shortcut_ids:
            self.pos_config_id.action_load_default_shortcuts()
        return self.pos_config_id.action_open_shortcuts()
