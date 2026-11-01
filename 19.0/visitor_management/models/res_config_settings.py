import secrets

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    visitor_notify_host = fields.Boolean(related='company_id.visitor_notify_host', readonly=False)
    visitor_max_hours = fields.Float(related='company_id.visitor_max_hours', readonly=False)
    visitor_kiosk_message = fields.Char(related='company_id.visitor_kiosk_message', readonly=False)
    visitor_kiosk_url = fields.Char('Kiosk URL', compute='_compute_visitor_kiosk_url')

    def _compute_visitor_kiosk_url(self):
        for settings in self:
            settings.visitor_kiosk_url = settings.company_id._visitor_kiosk_url()

    def action_visitor_new_kiosk_url(self):
        self.company_id.sudo().visitor_kiosk_token = secrets.token_urlsafe(16)
        return {'type': 'ir.actions.client', 'tag': 'reload'}
