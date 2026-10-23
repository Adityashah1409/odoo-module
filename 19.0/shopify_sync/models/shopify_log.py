from odoo import api, fields, models


class ShopifyLog(models.Model):
    _name = 'shopify.log'
    _description = 'Shopify Log'
    _order = 'id desc'

    instance_id = fields.Many2one('shopify.instance', ondelete='cascade', index=True)
    operation = fields.Char(required=True)
    level = fields.Selection([('info', 'Info'), ('warning', 'Warning'), ('error', 'Error')],
                             default='info', required=True)
    message = fields.Text(required=True)
    res_model = fields.Char()
    res_id = fields.Many2oneReference(model_field='res_model')

    @api.autovacuum
    def _gc_old(self):
        self.search([('create_date', '<', fields.Datetime.subtract(fields.Datetime.now(), days=60))]).unlink()
