from odoo import _, api, fields, models

from .pos_shortcut import DEFAULTS


class PosConfig(models.Model):
    _inherit = 'pos.config'

    shortcut_enabled = fields.Boolean("Keyboard shortcuts")
    shortcut_ids = fields.One2many('pos.shortcut', 'config_id', string="Shortcuts")

    def action_load_default_shortcuts(self):
        """Create the default shortcuts that are not defined yet (cash = c, bank = b)."""
        Shortcut = self.env['pos.shortcut']
        for config in self:
            existing = {(s.screen, s.key) for s in config.with_context(active_test=False).shortcut_ids}
            values = [{'config_id': config.id, 'screen': screen, 'action': action, 'key': key}
                      for screen, action, key in DEFAULTS if (screen, key) not in existing]
            cash = config.payment_method_ids.filtered(lambda m: m.type == 'cash')[:1]
            bank = config.payment_method_ids.filtered(lambda m: m.type != 'cash')[:1]
            for method, key in ((cash, 'c'), (bank, 'b')):
                if method and ('payment', key) not in existing:
                    values.append({'config_id': config.id, 'screen': 'payment', 'action': 'payment_method',
                                   'key': key, 'payment_method_id': method.id})
            Shortcut.create(values)
            config.shortcut_enabled = True
        return True

    def action_open_shortcuts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('pos_keyboard_shortcuts.action_pos_shortcut')
        action['domain'] = [('config_id', '=', self.id)]
        action['context'] = {'default_config_id': self.id, 'search_default_group_screen': 1}
        action['name'] = _("Keyboard shortcuts: %s", self.name)
        return action

    @api.model
    def _load_pos_data_read(self, records, config):
        result = super()._load_pos_data_read(records, config)
        if result:
            pos_config = self.browse(result[0]['id'])
            result[0]['_pos_shortcuts'] = pos_config.shortcut_ids._pos_data() if pos_config.shortcut_enabled else []
        return result
