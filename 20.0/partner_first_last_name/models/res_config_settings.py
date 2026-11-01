from odoo import api, fields, models

from .name_tools import ORDERS, join_name


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    partner_names_order = fields.Selection(ORDERS, string='Name order', default='first_last',
                                           config_parameter='partner_first_last_name.order')
    partner_names_middle = fields.Boolean('Middle names', config_parameter='partner_first_last_name.middle')
    partner_names_preview = fields.Char('Preview', compute='_compute_partner_names_preview')

    @api.depends('partner_names_order', 'partner_names_middle')
    def _compute_partner_names_preview(self):
        for settings in self:
            settings.partner_names_preview = join_name(
                'John', 'Paul' if settings.partner_names_middle else '', 'Smith',
                settings.partner_names_order or 'first_last')

    def action_partner_names_apply(self):
        ICP = self.env['ir.config_parameter'].sudo()
        # order the existing names were written in (the settings may already be saved with the new one)
        previous = ICP.get_str('partner_first_last_name.applied_order') or 'first_last'
        self.execute()
        filled, changed = self.env['res.partner']._partner_names_apply_order(previous)
        ICP.set_str('partner_first_last_name.applied_order', self.env['res.partner']._partner_names_settings()[0])
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success',
                           'message': self.env._('%(filled)s name(s) split, %(changed)s name(s) rewritten.',
                                                 filled=filled, changed=changed)}}
