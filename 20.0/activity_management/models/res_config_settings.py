from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    activity_reminder_enabled = fields.Boolean(
        'Activity reminders', config_parameter='activity_management.reminder_enabled')
    activity_reminder_days = fields.Integer(
        'Remind days before the deadline', config_parameter='activity_management.reminder_days')
    activity_overdue_digest = fields.Boolean(
        'Include overdue activities', config_parameter='activity_management.overdue_digest')
    activity_notify_supervisor = fields.Boolean(
        'Notify supervisors', config_parameter='activity_management.notify_supervisor',
        help='Supervisors are told when an activity of their team is cancelled or reassigned.')
    activity_mass_model_ids = fields.Many2many(
        'ir.model', string='Mass scheduling on', compute='_compute_activity_mass_model_ids',
        inverse='_inverse_activity_mass_model_ids', readonly=False,
        domain=[('transient', '=', False), ('is_mail_activity', '=', True)],
        help='Adds "Schedule activities" to the Action menu of these models.')

    def _compute_activity_mass_model_ids(self):
        models_ = self.env['activity.mass.schedule']._bound_models()
        for settings in self:
            settings.activity_mass_model_ids = models_

    def _inverse_activity_mass_model_ids(self):
        for settings in self:
            self.env['activity.mass.schedule']._sync_bindings(settings.activity_mass_model_ids)
