from odoo import api, fields, models

ORDERS = [('desc', 'Newest first'), ('asc', 'Oldest first')]


class ResUsers(models.Model):
    _inherit = 'res.users'

    chatter_message_order = fields.Selection(
        ORDERS, 'Chatter order', help='Order of the messages in the chatter of records. Empty: company default.')

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['chatter_message_order']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['chatter_message_order']

    def _chatter_effective_order(self):
        self.ensure_one()
        default = self.env['ir.config_parameter'].sudo().get_param('chatter_sort_by_date.default_order')
        return self.chatter_message_order or (default if default in ('asc', 'desc') else 'desc')

    @api.model
    def chatter_set_message_order(self, order):
        """ Called by the toggle in the chatter: remember the order for the current user. """
        if order not in ('asc', 'desc'):
            raise ValueError(order)
        self.env.user.sudo().chatter_message_order = order
        return order
