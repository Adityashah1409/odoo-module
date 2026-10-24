from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    am_export_alert_threshold = fields.Integer(
        'Export alert threshold', config_parameter='access_management.export_alert_threshold',
        help='E-mail an alert when one export contains at least this many records (0: no alert).')
    am_alert_emails = fields.Char('Alert e-mails', config_parameter='access_management.alert_emails',
                                  help='Comma-separated addresses for export alerts.')
    am_export_log_days = fields.Integer('Keep export logs (days)', config_parameter='access_management.export_log_days',
                                        default=90, help='0: keep forever.')
