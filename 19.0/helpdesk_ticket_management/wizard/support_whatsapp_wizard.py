from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError


class SupportWhatsappWizard(models.TransientModel):
    _name = 'support.whatsapp.wizard'
    _description = 'Send a ticket message by WhatsApp'

    ticket_id = fields.Many2one('support.ticket', required=True)
    phone = fields.Char(related='ticket_id.partner_phone', readonly=False)
    message = fields.Text(required=True, compute='_compute_message', store=True, readonly=False, precompute=True)

    @api.depends('ticket_id')
    def _compute_message(self):
        for wizard in self:
            ticket = wizard.ticket_id
            wizard.message = self.env._(
                'Hello %(name)s,\n\nAbout your ticket %(number)s "%(subject)s" (status: %(stage)s).\n'
                'Follow it here: %(url)s\n\n%(signature)s',
                name=ticket.partner_name or '', number=ticket.number, subject=ticket.name,
                stage=ticket.stage_id.name or '', url=ticket.get_base_url() + ticket.get_portal_url(),
                signature=self.env.user.name)

    def action_send(self):
        self.ensure_one()
        if not ''.join(c for c in (self.phone or '') if c.isdigit()):
            raise UserError(self.env._('Enter the phone number of the customer.'))
        self.ticket_id.message_post(
            body=Markup('<p><b>%s</b></p><p>%s</p>') % (
                self.env._('Sent by WhatsApp to %s', self.phone),
                Markup('<br/>').join(self.message.splitlines())),
            subtype_xmlid='mail.mt_note')
        return {'type': 'ir.actions.act_url', 'url': self.ticket_id._whatsapp_url(self.message), 'target': 'new'}
