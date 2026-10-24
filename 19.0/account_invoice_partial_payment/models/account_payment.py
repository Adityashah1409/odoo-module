from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    partial_batch_id = fields.Many2one('account.partial.payment', string='Partial payment batch',
                                       copy=False, index='btree_not_null', readonly=True)
