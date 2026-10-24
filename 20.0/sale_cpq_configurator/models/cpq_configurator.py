from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class CpqConfigurator(models.Model):
    _name = 'cpq.configurator'
    _description = 'CPQ Configurator'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True, help="Shown to sales people, e.g. 'Custom office desk'.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    product_tmpl_id = fields.Many2one(
        'product.template', string="Base product", required=True,
        help="Configured products are created from this product (category, taxes, unit, routes).")
    base_price = fields.Float(digits='Product Price', help="Price before options.")
    currency_id = fields.Many2one(related='company_id.currency_id')
    bom_type = fields.Selection([('normal', 'Manufacture (manufacturing order on confirmation)'),
                                 ('phantom', 'Kit (components delivered)')],
                                string="Fulfilment", default='normal', required=True)
    description = fields.Html(translate=True)
    section_ids = fields.One2many('cpq.section', 'configurator_id', copy=True)
    option_ids = fields.One2many('cpq.option', 'configurator_id', copy=True)
    price_rule_ids = fields.One2many('cpq.price.rule', 'configurator_id', copy=True)
    operation_ids = fields.One2many('cpq.operation', 'configurator_id', copy=True)
    configuration_count = fields.Integer(compute='_compute_configuration_count')

    def _compute_configuration_count(self):
        counts = dict(self.env['cpq.configuration']._read_group(
            [('configurator_id', 'in', self.ids)], ['configurator_id'], ['__count']))
        for configurator in self:
            configurator.configuration_count = counts.get(configurator, 0)

    def action_view_configurations(self):
        action = self.env['ir.actions.act_window']._for_xml_id('sale_cpq_configurator.action_cpq_configuration')
        action['domain'] = [('configurator_id', '=', self.id)]
        return action


class CpqSection(models.Model):
    _name = 'cpq.section'
    _description = 'CPQ Step'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    configurator_id = fields.Many2one('cpq.configurator', required=True, ondelete='cascade', index=True)
    selection = fields.Selection([('one', 'One choice'), ('multi', 'Several choices')], default='one', required=True)
    required = fields.Boolean(default=True, help="At least one option of this step must be selected.")
    option_ids = fields.One2many('cpq.option', 'section_id')


class CpqOption(models.Model):
    _name = 'cpq.option'
    _description = 'CPQ Option'
    _order = 'section_sequence, sequence, id'

    name = fields.Char(compute='_compute_name', store=True, readonly=False, translate=True)
    sequence = fields.Integer(default=10)
    configurator_id = fields.Many2one('cpq.configurator', required=True, ondelete='cascade', index=True)
    section_id = fields.Many2one('cpq.section', required=True, ondelete='cascade',
                                 domain="[('configurator_id', '=', configurator_id)]")
    section_sequence = fields.Integer("Step sequence", related='section_id.sequence', store=True)
    product_id = fields.Many2one('product.product', string="Component", required=True,
                                 help="Added to the bill of materials when the option is selected.")
    unit_price = fields.Float(compute='_compute_unit_price', store=True, readonly=False, digits='Product Price',
                              help="Price added per unit of this option (defaults to the component's sales price).")
    default_selected = fields.Boolean("Selected by default")
    default_qty = fields.Float(default=1.0, digits='Product Unit')
    min_qty = fields.Float(default=1.0, digits='Product Unit')
    max_qty = fields.Float(default=1.0, digits='Product Unit', help="0 = no maximum.")
    excluded_option_ids = fields.Many2many(
        'cpq.option', 'cpq_option_exclusion_rel', 'option_id', 'excluded_id', string="Not compatible with",
        domain="[('configurator_id', '=', configurator_id), ('id', '!=', id)]")
    required_option_ids = fields.Many2many(
        'cpq.option', 'cpq_option_requirement_rel', 'option_id', 'required_id', string="Requires one of",
        domain="[('configurator_id', '=', configurator_id), ('id', '!=', id)]")
    visible_if_option_ids = fields.Many2many(
        'cpq.option', 'cpq_option_visibility_rel', 'option_id', 'trigger_id', string="Only available with",
        domain="[('configurator_id', '=', configurator_id), ('id', '!=', id)]",
        help="The option can only be chosen when one of these options is selected.")

    @api.depends('product_id')
    def _compute_name(self):
        for option in self:
            if not option.name and option.product_id:
                option.name = option.product_id.display_name

    @api.depends('product_id')
    def _compute_unit_price(self):
        for option in self:
            if not option.unit_price and option.product_id:
                option.unit_price = option.product_id.lst_price

    @api.constrains('min_qty', 'max_qty', 'default_qty')
    def _check_quantities(self):
        for option in self:
            if option.min_qty <= 0:
                raise ValidationError(_("Minimum quantity of %s must be positive.", option.name))
            if option.max_qty and option.max_qty < option.min_qty:
                raise ValidationError(_("Maximum quantity of %s is below its minimum.", option.name))
            if option.default_qty < option.min_qty or (option.max_qty and option.default_qty > option.max_qty):
                raise ValidationError(_("Default quantity of %s is outside its limits.", option.name))


class CpqPriceRule(models.Model):
    _name = 'cpq.price.rule'
    _description = 'CPQ Price Rule'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    configurator_id = fields.Many2one('cpq.configurator', required=True, ondelete='cascade', index=True)
    rule_type = fields.Selection([('fixed', 'Add a fixed amount'), ('percent', 'Add a percentage'),
                                  ('discount', 'Discount (percentage)')], default='fixed', required=True)
    amount = fields.Float(help="Amount, or percentage for percentage rules.")
    condition_option_ids = fields.Many2many(
        'cpq.option', string="When all these options are selected",
        domain="[('configurator_id', '=', configurator_id)]", help="Empty = always.")
    min_quantity = fields.Float("From quantity", default=0.0, help="Only when the ordered quantity reaches this.")

    def _applies(self, selected_options, quantity):
        self.ensure_one()
        return self.condition_option_ids <= selected_options and quantity >= (self.min_quantity or 0.0)


class CpqOperation(models.Model):
    _name = 'cpq.operation'
    _description = 'CPQ Manufacturing Operation'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    configurator_id = fields.Many2one('cpq.configurator', required=True, ondelete='cascade', index=True)
    workcenter_id = fields.Many2one('mrp.workcenter', required=True)
    duration = fields.Float("Duration (min)", default=60.0)
    option_ids = fields.Many2many('cpq.option', string="Only with options",
                                  domain="[('configurator_id', '=', configurator_id)]",
                                  help="Empty = always included.")
