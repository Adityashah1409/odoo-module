import json
import logging

from odoo import api, fields, models

from . import queries
from .shopify_instance import ShopifyError, gid

_logger = logging.getLogger(__name__)


class ShopifyQueue(models.Model):
    """Incoming Shopify data (API imports and webhooks), processed one by one with retries."""
    _name = 'shopify.queue'
    _description = 'Shopify Sync Queue'
    _order = 'id desc'

    instance_id = fields.Many2one('shopify.instance', required=True, ondelete='cascade', index=True)
    data_type = fields.Selection([('product', 'Product'), ('customer', 'Customer'), ('order', 'Order')],
                                 required=True)
    source = fields.Selection([('import', 'Import'), ('webhook', 'Webhook')], default='import', required=True)
    shopify_id = fields.Char("Shopify ID", index=True)
    name = fields.Char()
    payload = fields.Text(help="JSON received from Shopify. Webhook lines only carry the id; data is fetched again.")
    state = fields.Selection([('draft', 'To process'), ('done', 'Done'), ('skipped', 'Skipped'), ('failed', 'Failed')],
                             default='draft', required=True, index=True)
    message = fields.Text()
    attempts = fields.Integer()
    res_model = fields.Char()
    res_id = fields.Many2oneReference(model_field='res_model')
    processed_date = fields.Datetime()

    @api.model
    def _add(self, instance, data_type, node, source='import'):
        return self.create({
            'instance_id': instance.id, 'data_type': data_type, 'source': source,
            'shopify_id': node.get('id'),
            'name': node.get('name') or node.get('title') or node.get('email') or node.get('id'),
            'payload': json.dumps(node),
        })

    def _process(self, max_attempts=3):
        for line in self.filtered(lambda l: l.state in ('draft', 'failed')):
            instance = line.instance_id.with_company(line.instance_id.company_id)
            try:
                with self.env.cr.savepoint():
                    data = json.loads(line.payload) if line.payload else {}
                    if line.source == 'webhook':
                        data = line._fetch(instance) or data
                    record = getattr(instance, f'_import_{line.data_type}')(data)
                line.write({
                    'state': 'done' if record else 'skipped',
                    'message': False if record else "Not imported (status filter or cancelled).",
                    'res_model': record._name if record else False,
                    'res_id': record[:1].id if record else False,
                    'processed_date': fields.Datetime.now(),
                })
            except (ShopifyError, ValueError, KeyError, TypeError) as e:
                _logger.info("Shopify queue line %s failed: %s", line.id, e)
                line.write({'state': 'failed', 'message': str(e) or repr(e), 'attempts': line.attempts + 1})
        return True

    def _fetch(self, instance):
        """Webhooks only give a REST payload: fetch the full record through GraphQL."""
        if self.data_type == 'order':
            return instance._graphql(queries.ORDER, {'id': gid('Order', self.shopify_id)})['order']
        return None

    def action_retry(self):
        self.filtered(lambda l: l.state == 'failed')._process()
        return True

    def action_open_record(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id,
                'views': [(False, 'form')]}

    @api.model
    def _cron_process(self):
        self.search([('state', '=', 'draft')], limit=200, order='id')._process()
        self.search([('state', '=', 'failed'), ('attempts', '<', 3)], limit=50, order='id')._process()

    @api.autovacuum
    def _gc_done(self):
        self.search([('state', 'in', ('done', 'skipped')),
                     ('processed_date', '<', fields.Datetime.subtract(fields.Datetime.now(), days=30))]).unlink()
