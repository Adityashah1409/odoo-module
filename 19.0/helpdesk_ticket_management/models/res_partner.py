from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    support_ticket_count = fields.Integer('Tickets', compute='_compute_support_ticket_count')

    def _compute_support_ticket_count(self):
        """Tickets of the partner and of its contacts."""
        Ticket = self.env['support.ticket'].with_context(active_test=False)
        for partner in self:
            partner.support_ticket_count = Ticket.search_count([('partner_id', 'child_of', partner.id)]) \
                if partner.id else 0

    def action_view_support_tickets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('helpdesk_ticket_management.action_support_ticket')
        action.update({'domain': [('partner_id', 'child_of', self.id)],
                       'context': {'default_partner_id': self.id, 'active_test': False}})
        return action
