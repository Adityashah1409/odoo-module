from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def _visible_menu_ids(self, debug=False):
        visible = super()._visible_menu_ids(debug)
        restrictions = self.env['access.rule']._get_restrictions()
        if not restrictions or not restrictions['menus']:
            return visible
        return frozenset(visible) - restrictions['menus']

    @api.model
    def _access_blocked_action(self, action):
        """True when ``action`` is only reachable from menus hidden to the current user."""
        restrictions = self.env['access.rule']._get_restrictions()
        if not restrictions or not restrictions['menus'] or not restrictions['block_menu_actions']:
            return False
        ref = f'{action._name},{action.id}'
        menus = self.sudo().search([('action', '=', ref)])
        return bool(menus) and set(menus.ids) <= restrictions['menus']
