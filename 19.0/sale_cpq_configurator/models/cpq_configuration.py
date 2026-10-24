from odoo import _, api, fields, models


def uom_field(env, model):
    """Unit field of BoM / BoM line: product_uom_id up to Odoo 19, uom_id from Odoo 20."""
    return 'uom_id' if 'uom_id' in env[model]._fields else 'product_uom_id'


class CpqConfiguration(models.Model):
    """A configuration chosen for one quotation line: options, price, generated product and BoM."""
    _name = 'cpq.configuration'
    _description = 'CPQ Configuration'
    _order = 'id desc'

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: _("New"))
    configurator_id = fields.Many2one('cpq.configurator', required=True, readonly=True, ondelete='restrict')
    order_id = fields.Many2one('sale.order', readonly=True, ondelete='cascade', index=True)
    sale_line_id = fields.Many2one('sale.order.line', readonly=True, ondelete='set null')
    partner_id = fields.Many2one(related='order_id.partner_id', store=True)
    quantity = fields.Float(readonly=True, digits='Product Unit')
    line_ids = fields.One2many('cpq.configuration.line', 'configuration_id', readonly=True)
    price_unit = fields.Float(readonly=True, digits='Product Price')
    currency_id = fields.Many2one(related='configurator_id.currency_id')
    summary = fields.Text(readonly=True)
    product_id = fields.Many2one('product.product', string="Configured product", readonly=True)
    bom_id = fields.Many2one('mrp.bom', readonly=True)
    production_ids = fields.One2many('mrp.production', 'cpq_configuration_id', readonly=True)
    state = fields.Selection([('quote', 'Quotation'), ('confirmed', 'Confirmed'), ('cancel', 'Cancelled')],
                             default='quote', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                vals['name'] = self.env['ir.sequence'].next_by_code('cpq.configuration') or _("New")
        return super().create(vals_list)

    def _create_product_and_bom(self):
        """A dedicated product and BoM per configuration, so kits and MOs behave natively."""
        for config in self:
            configurator = config.configurator_id
            base = configurator.product_tmpl_id
            template = base.copy({
                'name': f"{base.name} ({config.name})",
                'default_code': config.name,
                'list_price': config.price_unit,
                'sale_ok': True,
                'purchase_ok': False,
                'description_sale': config.summary,
                'type': 'consu',
                'is_storable': configurator.bom_type == 'normal',
            })
            product = template.product_variant_ids[:1]
            selected = config.line_ids.option_id
            bom = self.env['mrp.bom'].create({
                'product_tmpl_id': template.id,
                'product_id': product.id,
                'code': config.name,
                'type': configurator.bom_type,
                'product_qty': 1.0,
                'company_id': configurator.company_id.id or False,
            })
            line_uom = uom_field(self.env, 'mrp.bom.line')
            self.env['mrp.bom.line'].create([{
                'bom_id': bom.id, 'product_id': line.product_id.id, 'product_qty': line.quantity,
                line_uom: line.product_id.uom_id.id,
            } for line in config.line_ids])
            if configurator.bom_type == 'normal':
                for operation in configurator.operation_ids.filtered(
                        lambda op: not op.option_ids or op.option_ids & selected):
                    self.env['mrp.routing.workcenter'].create({
                        'bom_id': bom.id, 'name': operation.name, 'workcenter_id': operation.workcenter_id.id,
                        'time_cycle_manual': operation.duration, 'sequence': operation.sequence,
                    })
            config.write({'product_id': product.id, 'bom_id': bom.id})

    def _create_productions(self):
        """Manufacturing orders for confirmed 'manufacture' configurations."""
        Production = self.env['mrp.production']
        for config in self.filtered(lambda c: c.configurator_id.bom_type == 'normal' and not c.production_ids):
            line = config.sale_line_id
            production = Production.create({
                'product_id': config.product_id.id,
                'bom_id': config.bom_id.id,
                'product_qty': line.product_uom_qty if line else config.quantity,
                'origin': config.order_id.name,
                'company_id': config.order_id.company_id.id,
                'cpq_configuration_id': config.id,
            })
            production.action_confirm()
        self.write({'state': 'confirmed'})

    def action_view_productions(self):
        action = self.env['ir.actions.act_window']._for_xml_id('mrp.mrp_production_action')
        action['domain'] = [('id', 'in', self.production_ids.ids)]
        action['context'] = {}
        return action


class CpqConfigurationLine(models.Model):
    _name = 'cpq.configuration.line'
    _description = 'CPQ Configuration Line'
    _order = 'sequence, id'

    configuration_id = fields.Many2one('cpq.configuration', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer()
    section_name = fields.Char("Step")
    option_id = fields.Many2one('cpq.option', ondelete='set null')
    product_id = fields.Many2one('product.product', string="Component", required=True)
    quantity = fields.Float(digits='Product Unit')
    unit_price = fields.Float(digits='Product Price')
    subtotal = fields.Float(digits='Product Price')


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    cpq_configuration_id = fields.Many2one('cpq.configuration', readonly=True, index='btree_not_null', copy=False)
