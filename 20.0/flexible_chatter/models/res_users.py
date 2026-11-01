from odoo import api, fields, models
from odoo.exceptions import ValidationError

POSITIONS = [('auto', 'Automatic'), ('side', 'On the side'), ('bottom', 'Below the form')]
MIN_WIDTH, MAX_WIDTH = 20, 65


class ResUsers(models.Model):
    _inherit = 'res.users'

    chatter_position = fields.Selection(
        POSITIONS, 'Chatter position', user_writeable=True,
        help='Automatic: on the side on wide screens, below the form otherwise (Odoo default). '
             'On the side: from medium-size screens. Empty: company default.')
    chatter_width = fields.Integer(
        'Chatter width (%)', user_writeable=True, help='Width of the chatter on the side, in % of the page. 0: default width.')
    chatter_hidden = fields.Boolean('Chatter hidden', user_writeable=True, help='The chatter is folded; click it to open it again.')

    @api.constrains('chatter_width')
    def _check_chatter_width(self):
        for user in self:
            if user.chatter_width and not MIN_WIDTH <= user.chatter_width <= MAX_WIDTH:
                raise ValidationError(self.env._('The chatter width must be between %(min)s and %(max)s %%, or 0.',
                                                 min=MIN_WIDTH, max=MAX_WIDTH))

    @api.model
    def _flexible_chatter_width(self, width):
        width = int(width or 0)
        return 0 if width <= 0 else max(MIN_WIDTH, min(MAX_WIDTH, width))

    def _flexible_chatter_prefs(self):
        self.ensure_one()
        icp = self.env['ir.config_parameter'].sudo()
        position = self.chatter_position or icp.get_str('flexible_chatter.position') or 'auto'
        width = self.chatter_width or int(icp.get_str('flexible_chatter.width') or 0)
        return {
            'position': position if position in dict(POSITIONS) else 'auto',
            'width': self._flexible_chatter_width(width),
            'hidden': self.chatter_hidden,
        }

    @api.model
    def flexible_chatter_save(self, values):
        """ Called by the chatter (layout menu, width handle, hide button). """
        vals = {}
        if 'position' in values:
            if values['position'] not in dict(POSITIONS):
                raise ValueError(values['position'])
            vals['chatter_position'] = values['position']
        if 'width' in values:
            vals['chatter_width'] = self._flexible_chatter_width(values['width'])
        if 'hidden' in values:
            vals['chatter_hidden'] = bool(values['hidden'])
        if vals:
            self.env.user.sudo().write(vals)
        return self.env.user._flexible_chatter_prefs()
