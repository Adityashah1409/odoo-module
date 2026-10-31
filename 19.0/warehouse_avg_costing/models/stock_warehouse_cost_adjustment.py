from odoo import api, fields, models
from odoo.exceptions import UserError


class StockWarehouseCostAdjustment(models.Model):
    """Request to set the average cost of a product in one warehouse."""
    _name = 'stock.warehouse.cost.adjustment'
    _description = 'Warehouse cost adjustment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default=lambda self: self.env._('New'), readonly=True, copy=False)
    product_id = fields.Many2one('product.product', required=True, tracking=True,
                                 domain="[('is_storable', '=', True)]")
    warehouse_id = fields.Many2one('stock.warehouse', required=True, tracking=True,
                                   domain="[('company_id', '=', company_id)]")
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    current_cost = fields.Float('Current Cost', digits='Product Price', compute='_compute_current',
                                help='Average cost of the product in the warehouse now.')
    quantity = fields.Float('On Hand', digits='Product Unit', compute='_compute_current')
    new_cost = fields.Float('New Cost', digits='Product Price', required=True, tracking=True)
    value_change = fields.Monetary(compute='_compute_current')
    reason = fields.Text()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('to_approve', 'To Approve'),
        ('done', 'Applied'),
        ('refused', 'Refused'),
    ], default='draft', required=True, tracking=True, copy=False)
    requested_by = fields.Many2one('res.users', default=lambda self: self.env.user, readonly=True, copy=False)
    approved_by = fields.Many2one('res.users', readonly=True, copy=False)
    applied_date = fields.Datetime(readonly=True, copy=False)
    old_cost = fields.Float('Cost Before', digits='Product Price', readonly=True, copy=False)
    line_id = fields.Many2one('stock.warehouse.cost.line', string='History Line', readonly=True, copy=False)

    @api.depends('product_id', 'warehouse_id', 'company_id', 'new_cost', 'state')
    def _compute_current(self):
        Cost = self.env['stock.warehouse.cost'].sudo()
        for adjustment in self:
            row = Cost.search([('product_id', '=', adjustment.product_id.id),
                               ('warehouse_id', '=', adjustment.warehouse_id.id),
                               ('company_id', '=', adjustment.company_id.id)], limit=1) \
                if adjustment.product_id and adjustment.warehouse_id else Cost
            adjustment.current_cost = row.avg_cost if row else \
                adjustment.product_id.with_company(adjustment.company_id).standard_price
            adjustment.quantity = row.quantity
            adjustment.value_change = (adjustment.new_cost - adjustment.current_cost) * row.quantity \
                if adjustment.state not in ('done', 'refused') else 0.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', self.env._('New')) == self.env._('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('stock.warehouse.cost.adjustment') or '/'
        return super().create(vals_list)

    def _is_manager(self):
        return self.env.su or self.env.user.has_group('warehouse_avg_costing.group_wh_cost_manager')

    def _check_applicable(self):
        Cost = self.env['stock.warehouse.cost']
        for adjustment in self:
            if not Cost._applicable_products(adjustment.product_id, adjustment.company_id):
                raise UserError(self.env._(
                    '%s is not valued per warehouse: it needs the average cost method and warehouse costing '
                    'enabled for the company.', adjustment.product_id.display_name))
            if adjustment.new_cost < 0:
                raise UserError(self.env._('The new cost cannot be negative.'))

    def action_submit(self):
        self._check_applicable()
        for adjustment in self.filtered(lambda a: a.state == 'draft'):
            if adjustment.company_id.warehouse_cost_approval and not adjustment._is_manager():
                adjustment.state = 'to_approve'
                adjustment._notify_managers()
            else:
                adjustment._apply()
        return True

    def action_approve(self):
        if not self._is_manager():
            raise UserError(self.env._('Only Warehouse Costing managers can approve cost adjustments.'))
        self.filtered(lambda a: a.state == 'to_approve')._apply()
        self.activity_unlink(['mail.mail_activity_data_todo'])
        return True

    def action_refuse(self):
        if not self._is_manager():
            raise UserError(self.env._('Only Warehouse Costing managers can refuse cost adjustments.'))
        self.filtered(lambda a: a.state == 'to_approve').write({'state': 'refused', 'approved_by': self.env.uid})
        self.activity_unlink(['mail.mail_activity_data_todo'])
        return True

    def action_reset(self):
        self.filtered(lambda a: a.state == 'refused').write({'state': 'draft', 'approved_by': False})
        return True

    def _notify_managers(self):
        group = self.env.ref('warehouse_avg_costing.group_wh_cost_manager', raise_if_not_found=False)
        manager = group and group.user_ids.filtered(lambda u: not u.share and u.id != 1)[:1]
        if manager:
            self.activity_schedule('mail.mail_activity_data_todo', user_id=manager.id,
                                   summary=self.env._('Approve warehouse cost adjustment'))

    def _apply(self):
        self._check_applicable()
        Cost = self.env['stock.warehouse.cost'].sudo()
        for adjustment in self:
            product = adjustment.product_id.with_company(adjustment.company_id)
            old_company_cost = product.standard_price
            row = Cost._get_row(product, adjustment.warehouse_id.id, adjustment.company_id)
            old_cost = row.avg_cost
            line = row._book(0.0, kind='adjustment', set_avg=adjustment.new_cost, adjustment=adjustment,
                             note=adjustment.reason or adjustment.name)
            adjustment.write({'state': 'done', 'approved_by': self.env.uid, 'applied_date': fields.Datetime.now(),
                              'old_cost': old_cost, 'line_id': line.id})
            product.with_company(adjustment.company_id)._wh_sync_standard_price()
            # keep Odoo's own valuation history in line with the new company cost
            product.sudo().with_context(
                valuation_date=fields.Datetime.now())._change_standard_price({product: old_company_cost})
        return True
