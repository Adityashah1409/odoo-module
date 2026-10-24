from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .shopify_instance import ShopifyError


class ShopifyProductMap(models.Model):
    _name = 'shopify.product.map'
    _description = 'Shopify Product Variant Mapping'
    _order = 'instance_id, title, id'
    _rec_name = 'title'

    instance_id = fields.Many2one('shopify.instance', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', required=True, ondelete='cascade', index=True)
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id', store=True)
    title = fields.Char()
    sku = fields.Char("SKU")
    shopify_product_id = fields.Char("Shopify product ID", index=True)
    shopify_variant_id = fields.Char("Shopify variant ID", required=True)
    inventory_item_id = fields.Char("Inventory item ID")
    last_sync = fields.Datetime()

    _variant_uniq = models.Constraint('UNIQUE(instance_id, shopify_variant_id)', "Variant already mapped.")


class ShopifyCustomerMap(models.Model):
    _name = 'shopify.customer.map'
    _description = 'Shopify Customer Mapping'
    _rec_name = 'partner_id'

    instance_id = fields.Many2one('shopify.instance', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade', index=True)
    email = fields.Char(related='partner_id.email')
    shopify_customer_id = fields.Char("Shopify customer ID", required=True)

    _customer_uniq = models.Constraint('UNIQUE(instance_id, shopify_customer_id)', "Customer already mapped.")


class ShopifyExportProductWizard(models.TransientModel):
    _name = 'shopify.export.product.wizard'
    _description = 'Export products to Shopify'

    instance_id = fields.Many2one('shopify.instance', required=True, domain=[('state', '=', 'connected')])
    product_tmpl_ids = fields.Many2many('product.template', string="Products")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'product.template':
            values['product_tmpl_ids'] = [(6, 0, self.env.context.get('active_ids', []))]
        instances = self.env['shopify.instance'].search([('state', '=', 'connected')])
        if len(instances) == 1:
            values['instance_id'] = instances.id
        return values

    def action_export(self):
        errors = []
        for template in self.product_tmpl_ids:
            try:
                with self.env.cr.savepoint():
                    self.instance_id._export_product(template)
            except ShopifyError as e:
                errors.append(f"{template.display_name}: {e}")
                self.instance_id._log('export_product', str(e), level='error',
                                      res_model='product.template', res_id=template.id)
        if errors:
            raise UserError(_("Some products could not be exported:\n%s", '\n'.join(errors)))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': _("%s product(s) exported.", len(self.product_tmpl_ids)),
                           'next': {'type': 'ir.actions.act_window_close'}}}
