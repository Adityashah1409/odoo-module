from odoo import fields, models


class ActivityDoneWizard(models.TransientModel):
    _name = 'activity.done.wizard'
    _description = 'Mark activities as done with feedback'

    activity_ids = fields.Many2many('mail.activity', string='Activities', required=True)
    feedback = fields.Html()
    activity_count = fields.Integer(compute='_compute_activity_count')

    def _compute_activity_count(self):
        for wizard in self:
            wizard.activity_count = len(wizard.activity_ids)

    def action_done(self):
        self.activity_ids.filtered('active').action_feedback(feedback=self.feedback)
        return {'type': 'ir.actions.act_window_close'}

    def action_done_schedule_next(self):
        """Done, then open the scheduler for the next activity on the same document (one activity only)."""
        self.ensure_one()
        activity = self.activity_ids[:1]
        return activity.action_feedback_schedule_next(feedback=self.feedback)
