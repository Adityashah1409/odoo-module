from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    warehouse_costing = fields.Boolean(
        'Warehouse Average Costing',
        help='Keep one average cost per warehouse for products using the average cost method.')
    warehouse_cost_approval = fields.Boolean(
        'Approve Cost Adjustments',
        help='Cost adjustments requested by non-managers wait for a Warehouse Costing manager.')

    def action_wh_cost_initialize(self):
        """(Re)build the warehouse costs of the company from the stock on hand, at the current product cost."""
        for company in self:
            self.env['stock.warehouse.cost'].with_company(company)._initialize(company)
        return True
