from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    login_as_enabled = fields.Boolean('Login as other user', config_parameter='login_as_user.enabled')
    login_as_require_reason = fields.Boolean('Ask for a reason', config_parameter='login_as_user.require_reason')
    login_as_allow_portal = fields.Boolean('Allow portal users', config_parameter='login_as_user.allow_portal')
    login_as_notify_user = fields.Boolean('Notify the user', config_parameter='login_as_user.notify_user')
    login_as_max_minutes = fields.Integer('Switch back after (minutes)', config_parameter='login_as_user.max_minutes',
                                          help='Sessions opened as another user end automatically after this many '
                                               'minutes. 0 = no limit.')
