import re

from odoo import api, models

PARAM_PREFIX = 'my_backend_theme.'

COLOR_PATTERN = re.compile(r'^#[0-9a-fA-F]{6}$')

UI_SCALES = [
    ('90', '90%'),
    ('100', '100%'),
    ('110', '110%'),
    ('120', '120%'),
]

# Only the name of a font stack is stored; the stacks themselves live in the
# web client. Nothing is downloaded: a font is used when the device has it.
FONT_FAMILIES = [
    ('system', 'System default'),
    ('inter', 'Inter'),
    ('roboto', 'Roboto'),
    ('open_sans', 'Open Sans'),
    ('poppins', 'Poppins'),
]

# Every ir.config_parameter key the module owns, without PARAM_PREFIX.
CONFIG_KEYS = ('primary_color', 'navbar_color', 'ui_scale', 'font_family', 'reduce_motion')

DEFAULT_UI_SCALE = '100'
DEFAULT_FONT_FAMILY = 'system'


def is_valid_color(value):
    return bool(value) and bool(COLOR_PATTERN.match(value))


def sanitize_color(value):
    """Return ``value`` normalised to lowercase ``#rrggbb``, or False."""
    return value.lower() if isinstance(value, str) and is_valid_color(value) else False


def sanitize_choice(value, choices, default):
    return value if value in dict(choices) else default


class MyThemeConfig(models.AbstractModel):
    """Single entry point for reading the global (company-wide) theme
    configuration.

    Values are stored as ``ir.config_parameter`` records written by
    ``res.config.settings``. Everything read here is validated again before it
    reaches the web client, so a hand-edited parameter can never inject CSS.
    """

    _name = 'my.theme.config'
    _description = 'Backend Theme Configuration'

    @api.model
    def _get_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_str(PARAM_PREFIX + key)

    @api.model
    def _get_bool_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_bool(PARAM_PREFIX + key)

    @api.model
    def _get_global_config(self):
        """Theme settings shared by every user, as sent to the web client."""
        return {
            'primary_color': sanitize_color(self._get_param('primary_color')),
            'navbar_color': sanitize_color(self._get_param('navbar_color')),
            'ui_scale': int(sanitize_choice(self._get_param('ui_scale'), UI_SCALES, DEFAULT_UI_SCALE)),
            'font_family': sanitize_choice(self._get_param('font_family'), FONT_FAMILIES, DEFAULT_FONT_FAMILY),
            'reduce_motion': self._get_bool_param('reduce_motion'),
        }

    @api.model
    def _reset_global_config(self):
        self.env['ir.config_parameter'].sudo().search([
            ('key', 'in', [PARAM_PREFIX + key for key in CONFIG_KEYS]),
        ]).unlink()
