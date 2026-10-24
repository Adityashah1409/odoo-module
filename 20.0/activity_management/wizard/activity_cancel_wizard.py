from odoo import fields, models


class ActivityCancelWizard(models.TransientModel):
    _name = 'activity.cancel.wizard'
    _description = 'Cancel activities with a reason'

    activity_ids = fields.Many2many('mail.activity', string='Activities', required=True)
    reason = fields.Text(required=True)

    def action_confirm(self):
        self.activity_ids.action_cancel_with_reason(self.reason)
        return {'type': 'ir.actions.act_window_close'}
