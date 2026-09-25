from odoo import fields, models

from .theme_config import THEME_MODES, UI_SCALES

THEME_PREFERENCE_FIELDS = ('mbt_ui_scale', 'mbt_reduce_motion', 'mbt_theme_mode', 'mbt_sidebar_collapsed')


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

    def action_mbt_reset_preferences(self):
        self.ensure_one()
        self.write({fname: False for fname in THEME_PREFERENCE_FIELDS})
        return {'type': 'ir.actions.client', 'tag': 'reload'}
