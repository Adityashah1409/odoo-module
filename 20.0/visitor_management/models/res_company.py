import secrets

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    visitor_kiosk_token = fields.Char(copy=False, groups='base.group_system',
                                      default=lambda self: secrets.token_urlsafe(16))
    visitor_notify_host = fields.Boolean('Notify the host at check-in', default=True)
    visitor_max_hours = fields.Float('Automatic check-out after', default=12,
                                     help='Visitors still on site after this many hours are checked out by the '
                                          'scheduled action. 0 = never.')
    visitor_kiosk_message = fields.Char('Kiosk welcome text', translate=True)

    def _visitor_kiosk_url(self):
        self.ensure_one()
        token = self.sudo().visitor_kiosk_token
        if not token:
            token = self.sudo().visitor_kiosk_token = secrets.token_urlsafe(16)
        return f'{self.get_base_url()}/visitor/kiosk/{token}'
