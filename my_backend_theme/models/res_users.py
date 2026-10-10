from odoo import api, fields, models
from odoo.exceptions import AccessError

from .theme_config import THEME_MODES, UI_SCALES

THEME_PREFERENCE_FIELDS = (
    'mbt_ui_scale', 'mbt_reduce_motion', 'mbt_high_contrast', 'mbt_theme_mode', 'mbt_sidebar_collapsed',
)


class ResUsers(models.Model):
    _inherit = 'res.users'

    # Mirrors of the res.users.settings preferences so they can be edited from
    # the "My Preferences" form, which is a res.users form.
    mbt_ui_scale = fields.Selection(
        UI_SCALES,
        string="UI Scale",
        compute='_compute_mbt_preferences',
        inverse='_inverse_mbt_preferences',
        user_writeable=True,
        help="Leave empty to use the company default.",
    )
    mbt_reduce_motion = fields.Boolean(
        string="Reduce Motion",
        compute='_compute_mbt_preferences',
        inverse='_inverse_mbt_preferences',
        user_writeable=True,
        help="Turn off animations and transitions for you.",
    )
    mbt_high_contrast = fields.Boolean(
        string="High Contrast",
        compute='_compute_mbt_preferences',
        inverse='_inverse_mbt_preferences',
        user_writeable=True,
        help="Darker text, stronger borders, underlined links and a clearly visible keyboard focus.",
    )
    mbt_theme_mode = fields.Selection(
        THEME_MODES,
        string="Color Scheme",
        compute='_compute_mbt_preferences',
        inverse='_inverse_mbt_preferences',
        user_writeable=True,
        help="Leave empty to use the company default.",
    )
    mbt_sidebar_collapsed = fields.Boolean(
        string="Collapse Sidebar",
        compute='_compute_mbt_preferences',
        inverse='_inverse_mbt_preferences',
        user_writeable=True,
    )
    mbt_dark_mode_available = fields.Boolean(compute='_compute_mbt_dark_mode_available')

    def _compute_mbt_preferences(self):
        for user in self:
            settings = user.sudo().res_users_settings_id
            for fname in THEME_PREFERENCE_FIELDS:
                user[fname] = settings[fname] if settings else False

    def _inverse_mbt_preferences(self):
        for user in self:
            settings = self.env['res.users.settings']._find_or_create_for_user(user)
            settings.write({fname: user[fname] for fname in THEME_PREFERENCE_FIELDS})

    def _compute_mbt_dark_mode_available(self):
        available = self.env['my.theme.config']._get_global_config()['enable_dark_mode']
        self.mbt_dark_mode_available = available

    def _mbt_get_theme_mode(self):
        """The color scheme this user asked for: light, dark or system."""
        self.ensure_one()
        config = self.env['my.theme.config']._get_global_config()
        if not config['enable_dark_mode']:
            return 'light'
        settings = self.sudo().res_users_settings_id
        return (settings and settings.mbt_theme_mode) or config['default_theme_mode']

    @api.model
    def mbt_set_workspace_home(self, enabled):
        """Make My Workspace the current user's home page, or stop doing so.
        ``action_id`` is not writable by users themselves, hence the sudo,
        limited to the current user and to this one action."""
        if not self.env.user._is_internal():
            raise AccessError(self.env._("Only internal users have a backend home page."))
        action = self.env.ref('my_backend_theme.action_my_theme_workspace')
        user = self.env.user.sudo()
        if enabled:
            user.action_id = action.id
        elif user.action_id.id == action.id:
            user.action_id = False
        return bool(enabled)

    @api.model
    def mbt_is_workspace_home(self):
        action = self.env.ref('my_backend_theme.action_my_theme_workspace', raise_if_not_found=False)
        return bool(action) and self.env.user.sudo().action_id.id == action.id

    def action_mbt_reset_preferences(self):
        self.ensure_one()
        self.write({fname: False for fname in THEME_PREFERENCE_FIELDS})
        return {'type': 'ir.actions.client', 'tag': 'reload'}
