from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .theme_config import FONT_FAMILIES, UI_SCALES, DEFAULT_FONT_FAMILY, DEFAULT_UI_SCALE, is_valid_color


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    mbt_primary_color = fields.Char(
        string="Primary Color",
        config_parameter='my_backend_theme.primary_color',
        help="Color of primary buttons, links and highlights. Leave empty to keep Odoo's color.",
    )
    mbt_navbar_color = fields.Char(
        string="Navbar Color",
        config_parameter='my_backend_theme.navbar_color',
        help="Background color of the top navigation bar. Leave empty to keep Odoo's color.",
    )
    mbt_ui_scale = fields.Selection(
        UI_SCALES,
        string="Default UI Scale",
        default=DEFAULT_UI_SCALE,
        config_parameter='my_backend_theme.ui_scale',
        help="Text size of the backend. Each user can override it in their preferences.",
    )
    mbt_font_family = fields.Selection(
        FONT_FAMILIES,
        string="Font",
        default=DEFAULT_FONT_FAMILY,
        config_parameter='my_backend_theme.font_family',
        help="No font is downloaded: the chosen font is used when it is installed on the "
             "user's device, otherwise the system font is used.",
    )
    mbt_reduce_motion = fields.Boolean(
        string="Reduce Motion",
        config_parameter='my_backend_theme.reduce_motion',
        help="Turn off animations and transitions for every user.",
    )

    @api.constrains('mbt_primary_color', 'mbt_navbar_color')
    def _check_mbt_colors(self):
        for settings in self:
            for fname in ('mbt_primary_color', 'mbt_navbar_color'):
                value = settings[fname]
                if value and not is_valid_color(value):
                    raise ValidationError(_(
                        "%(field)s must be a hexadecimal color such as #1f6feb, not %(value)s.",
                        field=settings._fields[fname].string,
                        value=value,
                    ))

    def action_mbt_reset_defaults(self):
        self.env['my.theme.config']._reset_global_config()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
