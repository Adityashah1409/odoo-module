from odoo import fields, models

from .theme_config import UI_SCALES

THEME_PREFERENCE_FIELDS = ('mbt_ui_scale', 'mbt_reduce_motion')


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

    def _compute_mbt_preferences(self):
        for user in self:
            settings = user.sudo().res_users_settings_id
            for fname in THEME_PREFERENCE_FIELDS:
                user[fname] = settings[fname] if settings else False

    def _inverse_mbt_preferences(self):
        for user in self:
            settings = self.env['res.users.settings']._find_or_create_for_user(user)
            settings.write({fname: user[fname] for fname in THEME_PREFERENCE_FIELDS})

    def action_mbt_reset_preferences(self):
        self.ensure_one()
        self.write({'mbt_ui_scale': False, 'mbt_reduce_motion': False})
        return {'type': 'ir.actions.client', 'tag': 'reload'}
