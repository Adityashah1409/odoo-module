import json

from odoo import api, fields, models
from odoo.exceptions import UserError


class ActivityMassSchedule(models.TransientModel):
    _name = 'activity.mass.schedule'
    _description = 'Schedule activities for several records and users'

    res_model = fields.Char(required=True, readonly=True,
                            default=lambda self: self.env.context.get('active_model'))
    res_ids = fields.Char(readonly=True, default=lambda self: json.dumps(self.env.context.get('active_ids') or []))
    record_count = fields.Integer(compute='_compute_record_count')
    user_ids = fields.Many2many('res.users', string='Assign to', required=True, domain=[('share', '=', False)],
                                default=lambda self: self.env.user)
    activity_type_id = fields.Many2one('mail.activity.type', required=True,
                                       domain="['|', ('res_model', '=', False), ('res_model', '=', res_model)]")
    summary = fields.Char()
    note = fields.Html()
    date_deadline = fields.Date('Due date', required=True, default=fields.Date.context_today)
    priority = fields.Selection([('0', 'Normal'), ('1', 'Important'), ('2', 'Urgent')], default='0', required=True)
    tag_ids = fields.Many2many('mail.activity.tag', string='Tags')
    supervisor_id = fields.Many2one('res.users', domain=[('share', '=', False)],
                                    help="Leave empty to use each user's own supervisor.")

    @api.depends('res_ids')
    def _compute_record_count(self):
        for wizard in self:
            wizard.record_count = len(json.loads(wizard.res_ids or '[]'))

    @api.onchange('activity_type_id')
    def _onchange_activity_type_id(self):
        if self.activity_type_id and not self.summary:
            self.summary = self.activity_type_id.summary

    def action_schedule(self):
        """One activity per record and per user."""
        self.ensure_one()
        ids = json.loads(self.res_ids or '[]')
        records = self.env[self.res_model].browse(ids).exists()
        if not records:
            raise UserError(self.env._('Select at least one record.'))
        records.check_access('read')
        model = self.env['ir.model']._get(self.res_model)
        values = []
        for record in records:
            for user in self.user_ids:
                vals = {
                    'res_model_id': model.id, 'res_id': record.id, 'activity_type_id': self.activity_type_id.id,
                    'summary': self.summary, 'note': self.note, 'date_deadline': self.date_deadline,
                    'user_id': user.id, 'priority': self.priority, 'tag_ids': [(6, 0, self.tag_ids.ids)],
                }
                if self.supervisor_id:
                    vals['supervisor_id'] = self.supervisor_id.id
                values.append(vals)
        activities = self.env['mail.activity'].create(values)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': self.env._('%s activities scheduled.', len(activities)),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }

    # ------------------------------------------------------------------ Action menu bindings
    @api.model
    def _bound_models(self):
        actions = self.env['ir.actions.act_window'].sudo().search([
            ('res_model', '=', self._name), ('binding_model_id', '!=', False)])
        return actions.binding_model_id

    @api.model
    def _sync_bindings(self, models_):
        Action = self.env['ir.actions.act_window'].sudo()
        existing = Action.search([('res_model', '=', self._name), ('binding_model_id', '!=', False)])
        bound = existing.binding_model_id
        existing.filtered(lambda a: a.binding_model_id not in models_).unlink()
        for model in models_ - bound:
            Action.create({
                'name': self.env._('Schedule activities'), 'res_model': self._name, 'view_mode': 'form',
                'target': 'new', 'binding_model_id': model.id, 'binding_view_types': 'list,kanban,form',
            })
