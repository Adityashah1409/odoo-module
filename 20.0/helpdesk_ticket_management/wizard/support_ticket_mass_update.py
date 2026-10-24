from odoo import fields, models
from odoo.exceptions import UserError

from ..models.support_sla import PRIORITIES


class SupportTicketMassUpdate(models.TransientModel):
    _name = 'support.ticket.mass.update'
    _description = 'Update several tickets'

    ticket_ids = fields.Many2many('support.ticket', string='Tickets', required=True,
                                  default=lambda self: self.env['support.ticket'].browse(
                                      self.env.context.get('active_ids') or []))
    team_id = fields.Many2one('support.team')
    user_id = fields.Many2one('res.users', string='Assign to', domain=[('share', '=', False)])
    unassign = fields.Boolean('Remove the assignee')
    stage_id = fields.Many2one('support.stage')
    priority = fields.Selection(PRIORITIES)
    type_id = fields.Many2one('support.ticket.type')
    add_tag_ids = fields.Many2many('support.tag', 'support_mass_update_add_tag_rel', string='Add tags')
    remove_tag_ids = fields.Many2many('support.tag', 'support_mass_update_remove_tag_rel', string='Remove tags')
    follower_ids = fields.Many2many('res.partner', string='Add followers')
    ticket_count = fields.Integer(compute='_compute_ticket_count')

    def _compute_ticket_count(self):
        for wizard in self:
            wizard.ticket_count = len(wizard.ticket_ids)

    def action_apply(self):
        self.ensure_one()
        vals = {}
        for field in ('team_id', 'user_id', 'stage_id', 'type_id'):
            if self[field]:
                vals[field] = self[field].id
        if self.unassign:
            vals['user_id'] = False
        if self.priority:
            vals['priority'] = self.priority
        tags = [(4, t.id) for t in self.add_tag_ids] + [(3, t.id) for t in self.remove_tag_ids]
        if tags:
            vals['tag_ids'] = tags
        if not vals and not self.follower_ids:
            raise UserError(self.env._('Choose at least one change.'))
        if vals:
            self.ticket_ids.write(vals)
        if self.follower_ids:
            self.ticket_ids.message_subscribe(partner_ids=self.follower_ids.ids)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': self.env._('%s tickets updated.', len(self.ticket_ids)),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }
