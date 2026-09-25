from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from . import theme_config as tc

COLOR_FIELDS = ('mbt_primary_color', 'mbt_navbar_color', 'mbt_sidebar_color', 'mbt_accent_color')
SHORTCUT_FIELDS = (
    'mbt_shortcut_quick_create', 'mbt_shortcut_bookmarks', 'mbt_shortcut_recent',
    'mbt_shortcut_search', 'mbt_shortcut_dark_mode', 'mbt_shortcut_new_tab',
)
INT_FIELDS = {
    'mbt_sidebar_width': 'sidebar_width',
    'mbt_recent_limit': 'recent_limit',
    'mbt_max_tabs': 'max_tabs',
    'mbt_search_limit': 'search_limit',
}


def _param(key):
    return tc.PARAM_PREFIX + key


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Colors
    mbt_color_preset = fields.Selection(
        tc.COLOR_PRESET_SELECTION, string="Color Preset", default='custom',
        help="Fill the colors below from a ready-made palette. You can still adjust them afterwards.",
    )
    mbt_primary_color = fields.Char(
        string="Primary Color", config_parameter=_param('primary_color'),
        help="Color of primary buttons, links and highlights. Leave empty to keep Odoo's color.",
    )
    mbt_navbar_color = fields.Char(
        string="Navbar Color", config_parameter=_param('navbar_color'),
        help="Background color of the top navigation bar. Leave empty to keep Odoo's color.",
    )
    mbt_sidebar_color = fields.Char(
        string="Sidebar Color", config_parameter=_param('sidebar_color'),
        help="Background color of the sidebar menu. Leave empty to use the page background.",
    )
    mbt_accent_color = fields.Char(
        string="Accent Color", config_parameter=_param('accent_color'),
        help="Highlights the active app and menu in the sidebar.",
    )

    # General
    mbt_ui_scale = fields.Selection(
        tc.UI_SCALES, string="Default UI Scale", default='100', config_parameter=_param('ui_scale'),
        help="Text size of the backend. Each user can override it in their preferences.",
    )
    mbt_font_family = fields.Selection(
        tc.FONT_FAMILIES, string="Font", default='system', config_parameter=_param('font_family'),
        help="No font is downloaded: the chosen font is used when it is installed on the "
             "user's device, otherwise the system font is used.",
    )
    mbt_reduce_motion = fields.Boolean(
        string="Reduce Motion", config_parameter=_param('reduce_motion'),
        help="Turn off animations and transitions for every user.",
    )

    # Dark mode
    mbt_enable_dark_mode = fields.Boolean(
        string="Dark Mode", default=True, config_parameter=_param('enable_dark_mode'),
        help="Let users switch the backend to a dark color scheme.",
    )
    mbt_default_theme_mode = fields.Selection(
        tc.THEME_MODES, string="Default Color Scheme", default='light',
        config_parameter=_param('default_theme_mode'),
        help="Used for users who have not picked a color scheme themselves.",
    )

    # Navigation
    mbt_menu_style = fields.Selection(
        tc.MENU_STYLES, string="Menu Style", default='horizontal', config_parameter=_param('menu_style'),
        help="Where app menus are shown. On phones Odoo's own mobile menu is always used.",
    )
    mbt_sidebar_width = fields.Integer(
        string="Sidebar Width (px)", default=240, config_parameter=_param('sidebar_width'),
    )
    mbt_sidebar_hover_expand = fields.Boolean(
        string="Expand Sidebar on Hover", default=True, config_parameter=_param('sidebar_hover_expand'),
        help="Temporarily expand a collapsed sidebar while the pointer is over it.",
    )
    mbt_icon_style = fields.Selection(
        tc.ICON_STYLES, string="App Icon Style", default='default', config_parameter=_param('icon_style'),
    )
    mbt_compact_navbar = fields.Boolean(
        string="Compact Navbar", config_parameter=_param('compact_navbar'),
        help="Reduce the height of the top bar.",
    )

    # Views
    mbt_list_density = fields.Selection(
        tc.LIST_DENSITIES, string="List Row Density", default='default', config_parameter=_param('list_density'),
    )
    mbt_list_striped = fields.Boolean(string="Striped List Rows", config_parameter=_param('list_striped'))
    mbt_list_borderless = fields.Boolean(string="Borderless Lists", config_parameter=_param('list_borderless'))
    mbt_form_style = fields.Selection(
        tc.FORM_STYLES, string="Form Style", default='default', config_parameter=_param('form_style'),
    )
    mbt_form_sticky_statusbar = fields.Boolean(
        string="Sticky Form Status Bar", default=True, config_parameter=_param('form_sticky_statusbar'),
        help="Keep a form's buttons and status bar visible while scrolling.",
    )
    mbt_chatter_position = fields.Selection(
        tc.CHATTER_POSITIONS, string="Chatter Position", default='auto', config_parameter=_param('chatter_position'),
    )
    mbt_button_style = fields.Selection(
        tc.BUTTON_STYLES, string="Button Style", default='default', config_parameter=_param('button_style'),
    )
    mbt_checkbox_style = fields.Selection(
        tc.CHECKBOX_STYLES, string="Checkbox Style", default='default', config_parameter=_param('checkbox_style'),
    )
    mbt_scrollbar_style = fields.Selection(
        tc.SCROLLBAR_STYLES, string="Scrollbar Style", default='default', config_parameter=_param('scrollbar_style'),
    )
    mbt_rounded_fields = fields.Boolean(
        string="Rounded Input Fields", config_parameter=_param('rounded_fields'),
        help="Show editable fields as rounded boxes instead of underlines.",
    )

    # Productivity features
    mbt_enable_quick_create = fields.Boolean(
        string="Quick Create", default=True, config_parameter=_param('enable_quick_create'),
        help="Create records from anywhere with the + button in the top bar.",
    )
    mbt_enable_bookmarks = fields.Boolean(
        string="Bookmarks", default=True, config_parameter=_param('enable_bookmarks'),
        help="Let users bookmark any page or record.",
    )
    mbt_enable_recent = fields.Boolean(
        string="Recently Viewed", default=True, config_parameter=_param('enable_recent'),
        help="Remember the records each user opened.",
    )
    mbt_recent_limit = fields.Integer(
        string="Records Remembered", default=20, config_parameter=_param('recent_limit'),
        help="Older entries are deleted automatically (5 to 100).",
    )
    mbt_enable_tabs = fields.Boolean(
        string="Workspace Tabs", config_parameter=_param('enable_tabs'),
        help="Keep several pages open as tabs below the top bar.",
    )
    mbt_max_tabs = fields.Integer(
        string="Maximum Tabs", default=10, config_parameter=_param('max_tabs'),
        help="From 2 to 30. The oldest unpinned tab closes when the limit is reached.",
    )
    mbt_enable_split_view = fields.Boolean(
        string="Split View", default=True, config_parameter=_param('enable_split_view'),
        help="Browse a list and edit the selected record side by side.",
    )
    mbt_enable_global_search = fields.Boolean(
        string="Global Search", default=True, config_parameter=_param('enable_global_search'),
        help="Search records of several models at once from the command palette.",
    )
    mbt_search_limit = fields.Integer(
        string="Results per Model", default=5, config_parameter=_param('search_limit'),
        help="From 1 to 20.",
    )

    # Keyboard shortcuts
    mbt_shortcut_quick_create = fields.Char(
        string="Quick Create Shortcut", default='alt+shift+n', config_parameter=_param('shortcut_quick_create'),
    )
    mbt_shortcut_bookmarks = fields.Char(
        string="Bookmarks Shortcut", default='alt+shift+b', config_parameter=_param('shortcut_bookmarks'),
    )
    mbt_shortcut_recent = fields.Char(
        string="Recently Viewed Shortcut", default='alt+shift+r', config_parameter=_param('shortcut_recent'),
    )
    mbt_shortcut_search = fields.Char(
        string="Global Search Shortcut", default='alt+shift+f', config_parameter=_param('shortcut_search'),
    )
    mbt_shortcut_dark_mode = fields.Char(
        string="Dark Mode Shortcut", default='alt+shift+d', config_parameter=_param('shortcut_dark_mode'),
    )
    mbt_shortcut_new_tab = fields.Char(
        string="New Tab Shortcut", default='alt+shift+t', config_parameter=_param('shortcut_new_tab'),
    )

    @api.onchange('mbt_color_preset')
    def _onchange_mbt_color_preset(self):
        colors = tc.COLOR_PRESETS.get(self.mbt_color_preset)
        if colors:
            for key, value in colors.items():
                self['mbt_' + key] = value

    @api.constrains(*COLOR_FIELDS)
    def _check_mbt_colors(self):
        for settings in self:
            for fname in COLOR_FIELDS:
                value = settings[fname]
                if value and not tc.is_valid_color(value):
                    raise ValidationError(_(
                        "%(field)s must be a hexadecimal color such as #1f6feb, not %(value)s.",
                        field=settings._fields[fname].string,
                        value=value,
                    ))

    @api.constrains(*INT_FIELDS)
    def _check_mbt_numbers(self):
        for settings in self:
            for fname, key in INT_FIELDS.items():
                low, high = tc.CONFIG_SCHEMA[key][2]
                if not low <= settings[fname] <= high:
                    raise ValidationError(_(
                        "%(field)s must be between %(low)s and %(high)s.",
                        field=settings._fields[fname].string, low=low, high=high,
                    ))

    @api.constrains(*SHORTCUT_FIELDS)
    def _check_mbt_shortcuts(self):
        for settings in self:
            used = {}
            for fname in SHORTCUT_FIELDS:
                value = tc.normalize_hotkey(settings[fname] or '')
                if not value or value == 'none':
                    continue
                if not tc.is_valid_hotkey(value):
                    raise ValidationError(_(
                        "%(field)s: use a combination such as alt+shift+n (with control or alt), "
                        "or \"none\" to turn it off.",
                        field=settings._fields[fname].string,
                    ))
                if value in used:
                    raise ValidationError(_(
                        "%(first)s and %(second)s use the same shortcut.",
                        first=used[value], second=settings._fields[fname].string,
                    ))
                used[value] = settings._fields[fname].string

    def action_mbt_add_suggested_entries(self):
        self.env['my.theme.quick.create']._add_suggested_entries()
        self.env['my.theme.search.model']._add_suggested_entries()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _("Quick Create and Global Search now include the installed apps."),
            },
        }

    def action_mbt_reset_defaults(self):
        self.env['my.theme.config']._reset_global_config()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
