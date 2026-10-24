from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_partial_payment(self):
        """Open a draft batch for this partner with this invoice/bill pre-filled."""
        self.ensure_one()
        payment_type = 'inbound' if self.move_type == 'out_invoice' else 'outbound'
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Partial Payment'),
            'res_model': 'account.partial.payment',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_payment_type': payment_type,
                'default_partner_id': self.commercial_partner_id.id,
                'default_currency_id': self.currency_id.id,
                'default_amount': self.amount_residual,
                'default_line_ids': [(0, 0, {'move_id': self.id, 'amount': self.amount_residual})],
            },
        }
