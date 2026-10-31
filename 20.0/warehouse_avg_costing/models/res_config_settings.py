from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    warehouse_costing = fields.Boolean(related='company_id.warehouse_costing', readonly=False)
    warehouse_cost_approval = fields.Boolean(related='company_id.warehouse_cost_approval', readonly=False)

    def set_values(self):
        super().set_values()
        company = self.company_id
        # first activation: start from the stock on hand
        if company.warehouse_costing and \
                not self.env['stock.warehouse.cost'].sudo().search_count([('company_id', '=', company.id)], limit=1):
            company.action_wh_cost_initialize()

    def action_wh_cost_initialize(self):
        self.ensure_one()
        self.company_id.action_wh_cost_initialize()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': self.env._('Warehouse costs rebuilt from the stock on hand.')}}
