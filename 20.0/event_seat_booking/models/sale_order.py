from markupsafe import Markup

from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    seat_id = fields.Many2one('event.seat', string='Seat', copy=False, index='btree_not_null')
    seat_upgrade_registration_id = fields.Many2one('event.registration', string='Seat change for', copy=False)
    seat_upgrade_seat_id = fields.Many2one('event.seat', string='New seat', copy=False)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _seat_registrations(self):
        return self.order_line.registration_ids.filtered(lambda r: r.seat_id or r.seat_released_id)

    def action_confirm(self):
        res = super().action_confirm()
        # registration states are recomputed from the order (no write() on the registration)
        self.sudo()._seat_registrations()._seat_follow_state()
        for line in self.order_line.filtered(lambda l: l.seat_upgrade_registration_id and l.seat_upgrade_seat_id):
            registration = line.seat_upgrade_registration_id.sudo()
            seat = line.seat_upgrade_seat_id.sudo()
            if registration.seat_id != seat:
                registration.with_context(seat_hold_token=seat.hold_token).write({'seat_id': seat.id})
                registration.message_post(body=Markup('<p>%s</p>') % self.env._(
                    'Seat changed to %(seat)s (order %(order)s).', seat=seat.name, order=line.order_id.name))
        return res

    def _action_cancel(self):
        res = super()._action_cancel()
        self.sudo()._seat_registrations()._seat_follow_state()
        return res
