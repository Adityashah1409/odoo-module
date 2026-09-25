import re

from odoo import api, models

PARAM_PREFIX = 'my_backend_theme.'

COLOR_PATTERN = re.compile(r'^#[0-9a-fA-F]{6}$')
# Odoo hotkey syntax: modifiers in the order alt, control, shift, then one
# letter or digit. At least one of alt/control is required, otherwise the
# shortcut would fire while typing.
HOTKEY_PATTERN = re.compile(r'^(alt\+)?(control\+)?(shift\+)?[a-z0-9]$')

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

THEME_MODES = [
    ('light', 'Light'),
    ('dark', 'Dark'),
    ('system', 'Follow the device'),
]

MENU_STYLES = [
    ('horizontal', 'Top bar (Odoo default)'),
    ('sidebar', 'Sidebar'),
    ('compact', 'Compact sidebar'),
    ('icons', 'Icon-only sidebar'),
]

ICON_STYLES = [
    ('default', 'Original'),
    ('rounded', 'Rounded'),
    ('circle', 'Circle'),
    ('minimal', 'Monochrome'),
    ('glass', 'Glass'),
    ('outline', 'Outlined'),
]

LIST_DENSITIES = [
    ('compact', 'Compact'),
    ('default', 'Default'),
    ('comfortable', 'Comfortable'),
]

FORM_STYLES = [
    ('default', 'Default'),
    ('card', 'Card'),
    ('flat', 'Flat'),
    ('compact', 'Compact'),
]

CHATTER_POSITIONS = [
    ('auto', 'Automatic (Odoo default)'),
    ('bottom', 'Always below the form'),
    ('side', 'Beside the form on wide screens'),
]

BUTTON_STYLES = [
    ('default', 'Default'),
    ('rounded', 'Rounded'),
    ('square', 'Square'),
    ('pill', 'Pill'),
]

CHECKBOX_STYLES = [
    ('default', 'Default'),
    ('rounded', 'Rounded'),
    ('square', 'Square'),
]

SCROLLBAR_STYLES = [
    ('default', 'Browser default'),
    ('thin', 'Thin'),
    ('modern', 'Modern'),
]

# Color presets, all original palettes. ``custom`` leaves colors untouched and
# ``default`` clears them so Odoo's own colors are used.
COLOR_PRESETS = {
    'default': {'primary_color': False, 'navbar_color': False, 'sidebar_color': False, 'accent_color': False},
    'ocean': {'primary_color': '#1d6fb8', 'navbar_color': '#0b3558', 'sidebar_color': '#0f2a44', 'accent_color': '#38bdf8'},
    'royal': {'primary_color': '#6d4bc2', 'navbar_color': '#2e1f5e', 'sidebar_color': '#261a4d', 'accent_color': '#c4b5fd'},
    'forest': {'primary_color': '#2f7d4f', 'navbar_color': '#173d2a', 'sidebar_color': '#123223', 'accent_color': '#86efac'},
    'sunset': {'primary_color': '#c2551a', 'navbar_color': '#4a2412', 'sidebar_color': '#3b1d0f', 'accent_color': '#fdba74'},
    'crimson': {'primary_color': '#b42336', 'navbar_color': '#431018', 'sidebar_color': '#360d14', 'accent_color': '#fda4af'},
    'slate': {'primary_color': '#3f5c7a', 'navbar_color': '#1f2937', 'sidebar_color': '#111827', 'accent_color': '#93c5fd'},
}
COLOR_PRESET_SELECTION = [
    ('custom', 'Custom'),
    ('default', 'Odoo default'),
    ('ocean', 'Ocean'),
    ('royal', 'Royal'),
    ('forest', 'Forest'),
    ('sunset', 'Sunset'),
    ('crimson', 'Crimson'),
    ('slate', 'Slate'),
]

# Global configuration schema: key -> (kind, default, choices).
# ``kind`` is one of color, choice, bool, int. Every key is stored as the
# ir.config_parameter ``PARAM_PREFIX + key`` by res.config.settings.
CONFIG_SCHEMA = {
    # Colors
    'primary_color': ('color', False, None),
    'navbar_color': ('color', False, None),
    'sidebar_color': ('color', False, None),
    'accent_color': ('color', False, None),
    # Typography and general
    'ui_scale': ('choice', '100', UI_SCALES),
    'font_family': ('choice', 'system', FONT_FAMILIES),
    'reduce_motion': ('bool', False, None),
    # Dark mode
    'enable_dark_mode': ('bool', True, None),
    'default_theme_mode': ('choice', 'light', THEME_MODES),
    # Navigation
    'menu_style': ('choice', 'horizontal', MENU_STYLES),
    'sidebar_width': ('int', 240, (180, 360)),
    'sidebar_hover_expand': ('bool', True, None),
    'icon_style': ('choice', 'default', ICON_STYLES),
    'compact_navbar': ('bool', False, None),
    # Views
    'list_density': ('choice', 'default', LIST_DENSITIES),
    'list_striped': ('bool', False, None),
    'list_borderless': ('bool', False, None),
    'form_style': ('choice', 'default', FORM_STYLES),
    'form_sticky_statusbar': ('bool', True, None),
    'chatter_position': ('choice', 'auto', CHATTER_POSITIONS),
    'button_style': ('choice', 'default', BUTTON_STYLES),
    'checkbox_style': ('choice', 'default', CHECKBOX_STYLES),
    'scrollbar_style': ('choice', 'default', SCROLLBAR_STYLES),
    'rounded_fields': ('bool', False, None),
    # Productivity features
    'enable_quick_create': ('bool', True, None),
    'enable_bookmarks': ('bool', True, None),
    'enable_recent': ('bool', True, None),
    'recent_limit': ('int', 20, (5, 100)),
    'enable_tabs': ('bool', False, None),
    'max_tabs': ('int', 10, (2, 30)),
    'enable_split_view': ('bool', True, None),
    'enable_global_search': ('bool', True, None),
    'search_limit': ('int', 5, (1, 20)),
    # Keyboard shortcuts (Odoo hotkey syntax, e.g. "alt+shift+n")
    'shortcut_quick_create': ('hotkey', 'alt+shift+n', None),
    'shortcut_bookmarks': ('hotkey', 'alt+shift+b', None),
    'shortcut_recent': ('hotkey', 'alt+shift+r', None),
    'shortcut_search': ('hotkey', 'alt+shift+f', None),
    'shortcut_dark_mode': ('hotkey', 'alt+shift+d', None),
    'shortcut_new_tab': ('hotkey', 'alt+shift+t', None),
}

CONFIG_KEYS = tuple(CONFIG_SCHEMA)


def is_valid_color(value):
    return bool(value) and bool(COLOR_PATTERN.match(value))


def sanitize_color(value):
    """Return ``value`` normalised to lowercase ``#rrggbb``, or False."""
    return value.lower() if isinstance(value, str) and is_valid_color(value) else False


HOTKEY_MODIFIER_ALIASES = {'ctrl': 'control', 'cmd': 'control', 'option': 'alt'}
HOTKEY_MODIFIER_ORDER = ('alt', 'control', 'shift')


def normalize_hotkey(value):
    """Write a shortcut the way Odoo's hotkey service reports it: lowercase,
    modifiers in the order alt, control, shift. "Ctrl+Alt+K" becomes
    "alt+control+k". Unknown parts are kept so validation can reject them."""
    if not isinstance(value, str):
        return value
    parts = [part.strip() for part in value.strip().lower().split('+') if part.strip()]
    parts = [HOTKEY_MODIFIER_ALIASES.get(part, part) for part in parts]
    modifiers = [m for m in HOTKEY_MODIFIER_ORDER if m in parts[:-1]]
    others = [part for part in parts[:-1] if part not in HOTKEY_MODIFIER_ORDER]
    return '+'.join(modifiers + others + parts[-1:])


def is_valid_hotkey(value):
    return (
        isinstance(value, str)
        and bool(HOTKEY_PATTERN.match(value))
        and ('control+' in value or 'alt+' in value)
    )


def sanitize_choice(value, choices, default):
    return value if value in dict(choices) else default


def sanitize_int(value, bounds, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    low, high = bounds
    return value if low <= value <= high else default


def sanitize_value(key, value):
    """Validate one configuration value against CONFIG_SCHEMA.

    Invalid values fall back to the key's default, so a hand-edited parameter
    can never reach the web client.
    """
    kind, default, extra = CONFIG_SCHEMA[key]
    if kind == 'color':
        return sanitize_color(value)
    if kind == 'choice':
        return sanitize_choice(value, extra, default)
    if kind == 'int':
        return sanitize_int(value, extra, default)
    if kind == 'hotkey':
        value = normalize_hotkey(value)
        # An explicitly cleared shortcut is stored as "none".
        if value == 'none':
            return False
        return value if is_valid_hotkey(value) else default
    if kind == 'bool':
        if isinstance(value, bool):
            return value
        if value in ('True', 'true', '1'):
            return True
        if value in ('False', 'false', '0'):
            return False
        return default
    raise ValueError(key)


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
    def _get_raw_values(self):
        ICP = self.env['ir.config_parameter'].sudo()
        params = ICP.search([('key', 'in', [PARAM_PREFIX + key for key in CONFIG_KEYS])])
        return {param.key[len(PARAM_PREFIX):]: param.value for param in params}

    @api.model
    def _get_global_config(self):
        """Theme settings shared by every user, as sent to the web client."""
        raw = self._get_raw_values()
        return {
            # An empty value means "undefined" for ir.config_parameter.
            key: sanitize_value(key, raw[key]) if raw.get(key) else CONFIG_SCHEMA[key][1]
            for key in CONFIG_KEYS
        }

    @api.model
    def _set_global_config(self, values):
        """Store validated values; unknown keys are ignored."""
        ICP = self.env['ir.config_parameter'].sudo()
        for key, value in values.items():
            if key not in CONFIG_SCHEMA:
                continue
            value = sanitize_value(key, value)
            kind = CONFIG_SCHEMA[key][0]
            param = PARAM_PREFIX + key
            if kind == 'hotkey':
                ICP.set_str(param, value or 'none')
            elif kind == 'bool':
                ICP.set_bool(param, value)
            elif kind == 'int':
                ICP.set_int(param, value)
            else:
                ICP.set_str(param, value or None)

    @api.model
    def _reset_global_config(self):
        self.env['ir.config_parameter'].sudo().search([
            ('key', 'in', [PARAM_PREFIX + key for key in CONFIG_KEYS]),
        ]).unlink()
