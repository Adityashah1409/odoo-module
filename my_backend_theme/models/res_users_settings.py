from odoo import fields, models

from .theme_config import THEME_MODES, UI_SCALES


class ResUsersSettings(models.Model):
    _inherit = 'res.users.settings'

    # Per-user theme preferences. They reach the web client through
    # ``user.settings`` and are written with ``user.setUserSettings``; the
    # existing record rules already restrict each user to their own row.
    mbt_ui_scale = fields.Selection(
        UI_SCALES,
        string="UI Scale",
        help="Leave empty to use the company default.",
    )
    mbt_reduce_motion = fields.Boolean(string="Reduce Motion")
    mbt_theme_mode = fields.Selection(
        THEME_MODES,
        string="Color Scheme",
        help="Leave empty to use the company default.",
    )
    mbt_sidebar_collapsed = fields.Boolean(string="Collapse Sidebar")
