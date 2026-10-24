from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class SupportTicketMerge(models.TransientModel):
    _name = 'support.ticket.merge'
    _description = 'Merge tickets'

    ticket_ids = fields.Many2many('support.ticket', string='Tickets', required=True,
                                  default=lambda self: self._default_ticket_ids())
    target_id = fields.Many2one('support.ticket', string='Keep', required=True,
                                domain="[('id', 'in', ticket_ids)]",
                                default=lambda self: self._default_ticket_ids().sorted('id')[:1])
    warning = fields.Char(compute='_compute_warning')

    def _default_ticket_ids(self):
        if self.env.context.get('active_model') == 'support.ticket':
            return self.env['support.ticket'].browse(self.env.context.get('active_ids') or [])
        return self.env['support.ticket']

    @api.depends('ticket_ids')
    def _compute_warning(self):
        for wizard in self:
            partners = wizard.ticket_ids.partner_id.commercial_partner_id
            wizard.warning = self.env._('These tickets belong to different customers: %s.',
                                        ', '.join(partners.mapped('name'))) if len(partners) > 1 else False

    def action_merge(self):
        """Move conversation, attachments, followers, checklist and time to the kept ticket, close the others."""
        self.ensure_one()
        target = self.target_id
        others = self.ticket_ids - target
        if not others:
            raise UserError(self.env._('Select at least two tickets.'))
        others.check_access('write')
        target.check_access('write')
        sudo_others = others.sudo()
        sudo_others.message_ids.write({'res_id': target.id})
        self.env['ir.attachment'].sudo().search([('res_model', '=', 'support.ticket'),
                                                 ('res_id', 'in', others.ids)]).write({'res_id': target.id})
        sudo_others.checklist_ids.write({'ticket_id': target.id})
        sudo_others.time_entry_ids.write({'ticket_id': target.id})
        target.message_subscribe(partner_ids=sudo_others.message_partner_ids.ids)
        target.write({
            'tag_ids': [(4, tag.id) for tag in others.tag_ids],
            'priority': max([target.priority] + others.mapped('priority')),
            'description': Markup('').join([target.description or Markup('')] + [
                Markup('<hr/><p><b>%s</b></p>%s') % (t.display_name, t.description or '') for t in others]),
        })
        for ticket in others:
            close_stage = ticket.team_id._get_close_stage() if ticket.team_id else ticket.stage_id
            ticket.write({'merged_into_id': target.id, 'stage_id': close_stage.id, 'active': False})
        target.message_post(
            body=Markup('<p>%s</p>') % self.env._('Merged with %s.', ', '.join(others.mapped('display_name'))),
            subtype_xmlid='mail.mt_note')
        return {'type': 'ir.actions.act_window', 'res_model': 'support.ticket', 'res_id': target.id,
                'view_mode': 'form', 'views': [(False, 'form')], 'target': 'current'}
