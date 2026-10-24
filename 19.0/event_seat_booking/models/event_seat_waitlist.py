from odoo import api, fields, models


class EventSeatWaitlist(models.Model):
    _name = 'event.seat.waitlist'
    _description = 'Seat waitlist'
    _order = 'id'

    event_id = fields.Many2one('event.event', required=True, ondelete='cascade', index=True)
    ticket_id = fields.Many2one('event.event.ticket', string='Section', domain="[('event_id', '=', event_id)]")
    name = fields.Char(required=True)
    email = fields.Char(required=True)
    phone = fields.Char()
    seats_wanted = fields.Integer('Seats', default=1)
    state = fields.Selection([('waiting', 'Waiting'), ('notified', 'Notified'), ('registered', 'Registered'),
                              ('cancel', 'Cancelled')], default='waiting', required=True)
    notified_on = fields.Datetime(readonly=True)

    _event_email_uniq = models.Constraint('UNIQUE(event_id, email)', 'You are already on the waitlist of this event.')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('email'):
                vals['email'] = vals['email'].strip().lower()
        return super().create(vals_list)

    def _notify(self):
        template = self.env.ref('event_seat_booking.mail_template_seat_waitlist', raise_if_not_found=False)
        for entry in self:
            if template:
                template.send_mail(entry.id, force_send=False, email_layout_xmlid='mail.mail_notification_light')
        self.write({'state': 'notified', 'notified_on': fields.Datetime.now()})

    def action_notify(self):
        self._notify()
        return True

    def action_cancel(self):
        self.write({'state': 'cancel'})
        return True
