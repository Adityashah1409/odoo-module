from odoo import fields, models

from .whapi_account import chat_id_for_phone


class ResPartner(models.Model):
    _inherit = 'res.partner'

    whapi_chat_ids = fields.One2many('whapi.chat', 'partner_id', string='WhatsApp chats')
    whapi_message_count = fields.Integer(compute='_compute_whapi_message_count',
                                         groups='whatsapp_whapi.group_whapi_user')

    def _compute_whapi_message_count(self):
        counts = dict(self.env['whapi.message']._read_group([('partner_id', 'in', self.ids)], ['partner_id'],
                                                             ['__count']))
        for partner in self:
            partner.whapi_message_count = counts.get(partner, 0)

    def _whapi_get_chat(self, account):
        """Chat with this contact on ``account`` (created from the phone number when missing)."""
        self.ensure_one()
        chat = self.env['whapi.chat'].search([('partner_id', '=', self.id), ('account_id', '=', account.id),
                                              ('chat_type', '=', 'contact')], limit=1)
        if chat:
            return chat
        country = self.country_id or self.company_id.country_id or self.env.company.country_id
        wa_id = chat_id_for_phone(self.phone, country.phone_code)
        if not wa_id:
            return chat
        chat = account._whapi_get_chat(wa_id, self.name, partner=self)
        if not chat.partner_id:
            chat.partner_id = self
        return chat

    def action_whapi_open_chat(self):
        self.ensure_one()
        account = self.env['whapi.account'].search([('company_id', 'in', self.env.companies.ids)], limit=1)
        chat = self._whapi_get_chat(account) if account else self.env['whapi.chat']
        params = {'chat_id': chat.id} if chat else {}
        return {'type': 'ir.actions.client', 'tag': 'whatsapp_whapi.chat', 'name': self.name, 'params': params}

    def action_whapi_send(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': 'whapi.composer', 'view_mode': 'form', 'target': 'new',
            'name': self.env._('Send by WhatsApp'),
            'context': {'active_model': 'res.partner', 'active_ids': self.ids, 'active_id': self[:1].id},
        }
