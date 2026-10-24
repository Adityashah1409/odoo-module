from odoo import fields, models


class ShopifyLocation(models.Model):
    _name = 'shopify.location'
    _description = 'Shopify Location'
    _order = 'instance_id, name'

    instance_id = fields.Many2one('shopify.instance', required=True, ondelete='cascade', index=True)
    name = fields.Char(required=True)
    shopify_id = fields.Char("Shopify ID", required=True)
    active = fields.Boolean(default=True)
    warehouse_id = fields.Many2one('stock.warehouse', help="Stock of this warehouse is exported to the location.")
    export_stock = fields.Boolean(default=True)

    _shopify_uniq = models.Constraint('UNIQUE(instance_id, shopify_id)', "Location already imported.")
