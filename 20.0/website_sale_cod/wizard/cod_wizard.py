from odoo import api, fields, models
from odoo.exceptions import UserError


class SaleCodCollectWizard(models.TransientModel):
    _name = 'sale.cod.collect.wizard'
    _description = 'Collect cash on delivery'

    collection_id = fields.Many2one('sale.cod.collection', required=True)
    order_id = fields.Many2one(related='collection_id.order_id')
    partner_id = fields.Many2one(related='collection_id.partner_id')
    currency_id = fields.Many2one(related='collection_id.currency_id')
    amount_due = fields.Monetary(related='collection_id.amount_due')
    otp_required = fields.Boolean(compute='_compute_otp_required')
    code = fields.Char('Delivery code')
    amount = fields.Monetary('Amount received')
    driver_id = fields.Many2one('res.users', 'Delivery person', default=lambda self: self.env.user,
                                domain=[('share', '=', False)])
    note = fields.Text()
    error = fields.Char(readonly=True)

    @api.depends('collection_id')
    def _compute_otp_required(self):
        for wizard in self:
            wizard.otp_required = wizard.collection_id.sudo()._cod_code_required()

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        collection = self.env['sale.cod.collection'].browse(values.get('collection_id'))
        if collection and 'amount' in fields_list:
            values['amount'] = collection.amount_due
        return values

    def action_confirm(self):
        self.ensure_one()
        collection = self.collection_id
        if self.otp_required and not collection._cod_check_code(self.code):
            # the wrong attempt is counted: reopen the wizard with the error instead of raising
            self.error = self.env._('Wrong delivery code (%(left)s attempt(s) left).',
                                    left=max(5 - collection.otp_attempts, 0))
            self.code = False
            return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                    'view_mode': 'form', 'target': 'new', 'name': self.env._('Collect %s', collection.name)}
        collection._cod_collect(self.code, self.amount, driver=self.driver_id, note=self.note, code_checked=True)
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': self.env._('%s collected.', collection.name),
                           'next': {'type': 'ir.actions.act_window_close'}}}


class SaleCodCancelWizard(models.TransientModel):
    _name = 'sale.cod.cancel.wizard'
    _description = 'Cancel cash on delivery collections'

    collection_ids = fields.Many2many('sale.cod.collection', required=True)
    reason = fields.Selection([('refused', 'Customer refused the parcel'), ('absent', 'Customer not at home'),
                               ('no_cash', 'Customer could not pay'), ('address', 'Wrong address'),
                               ('other', 'Other')], required=True, default='refused')
    details = fields.Text()

    def action_cancel(self):
        if not self.env.user.has_group('sales_team.group_sale_salesman') and not self.env.su:
            raise UserError(self.env._('Only sales people can cancel a collection.'))
        label = dict(self._fields['reason'].selection)[self.reason]
        self.collection_ids._cod_cancel(f'{label}. {self.details}' if self.details else label)
        return {'type': 'ir.actions.act_window_close'}
