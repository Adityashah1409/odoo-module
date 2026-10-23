import base64
import hashlib
import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

TOPICS = {
    'orders/create': 'order', 'orders/updated': 'order', 'orders/paid': 'order', 'orders/cancelled': 'order',
    'products/create': 'product', 'products/update': 'product',
    'customers/create': 'customer', 'customers/update': 'customer',
}


def verify_hmac(secret, body, signature):
    if not secret or not signature:
        return False
    digest = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(digest, signature)


class ShopifyWebhook(http.Controller):

    @http.route('/shopify_sync/webhook/<int:instance_id>', type='http', auth='public', methods=['POST'], csrf=False)
    def webhook(self, instance_id, **kwargs):
        """Receive a Shopify webhook, check its signature and queue it (processed by a cron)."""
        body = request.httprequest.get_data()
        env = request.env(su=True)
        instance = env['shopify.instance'].browse(instance_id).exists()
        if not instance or not instance.active:
            return request.make_response('unknown store', status=404)
        if not verify_hmac(instance.webhook_secret, body, request.httprequest.headers.get('X-Shopify-Hmac-Sha256')):
            _logger.warning("Shopify webhook with an invalid signature for store %s", instance_id)
            return request.make_response('invalid signature', status=401)
        topic = request.httprequest.headers.get('X-Shopify-Topic', '')
        data_type = TOPICS.get(topic)
        if not data_type:
            return request.make_response('ignored', status=200)
        payload = json.loads(body or b'{}')
        kind = {'order': 'Order', 'product': 'Product', 'customer': 'Customer'}[data_type]
        node = {'id': f"gid://shopify/{kind}/{payload.get('id')}", 'name': payload.get('name') or payload.get('title')}
        if data_type == 'customer':
            node.update({'firstName': payload.get('first_name'), 'lastName': payload.get('last_name'),
                         'email': payload.get('email'), 'phone': payload.get('phone')})
            env['shopify.queue']._add(instance, data_type, node, source='import')
        elif data_type == 'order':
            env['shopify.queue']._add(instance, data_type, node, source='webhook')
        else:
            env['shopify.queue']._add(instance, data_type, payload_to_product(payload, node), source='import')
        return request.make_response('ok', status=200)


def payload_to_product(payload, node):
    """Convert a REST product webhook payload into the GraphQL shape used by the importer."""
    node.update({
        'title': payload.get('title'),
        'options': [{'name': o.get('name'), 'optionValues': [{'name': v} for v in o.get('values', [])]}
                    for o in payload.get('options', [])],
        'variants': {'nodes': [{
            'id': f"gid://shopify/ProductVariant/{v.get('id')}",
            'title': v.get('title'), 'sku': v.get('sku'), 'barcode': v.get('barcode'), 'price': v.get('price'),
            'inventoryItem': {'id': f"gid://shopify/InventoryItem/{v.get('inventory_item_id')}"},
            'selectedOptions': [{'name': o.get('name'), 'value': v.get(f'option{i + 1}')}
                                for i, o in enumerate(payload.get('options', [])) if v.get(f'option{i + 1}')],
        } for v in payload.get('variants', [])]},
    })
    return node
