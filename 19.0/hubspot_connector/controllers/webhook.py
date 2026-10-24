import json
import logging

from odoo import http
from odoo.http import request

from ..models.hubspot_client import verify_signature_v3

_logger = logging.getLogger(__name__)

# legacy subscription prefixes and generic object type ids -> object types of this module
EVENT_OBJECTS = {'contact': 'contacts', 'company': 'companies', 'deal': 'deals', 'product': 'products',
                 '0-1': 'contacts', '0-2': 'companies', '0-3': 'deals', '0-7': 'products', '0-14': 'quotes',
                 '0-53': 'invoices'}


class HubspotWebhook(http.Controller):

    @http.route('/hubspot/webhook/<int:account_id>', type='http', auth='none', methods=['POST'], csrf=False,
                save_session=False, readonly=False)
    def hubspot_webhook(self, account_id, **kwargs):
        env = request.env(su=True)
        account = env['hubspot.account'].browse(account_id).exists()
        if not account or not account.active:
            return request.make_json_response({'error': 'unknown account'}, status=404)
        body = request.httprequest.get_data()
        httpreq = request.httprequest
        if not verify_signature_v3(account.webhook_secret, httpreq.method, httpreq.url, body,
                                   httpreq.headers.get('X-HubSpot-Request-Timestamp'),
                                   httpreq.headers.get('X-HubSpot-Signature-v3')):
            _logger.warning('HubSpot webhook for account %s refused: bad signature', account_id)
            return request.make_json_response({'error': 'invalid signature'}, status=401)
        try:
            events = json.loads(body or b'[]')
        except ValueError:
            return request.make_json_response({'error': 'invalid JSON'}, status=400)
        if isinstance(events, dict):
            events = [events]
        enabled = {o.object_type for o in account.object_ids if o.import_enabled}
        values, seen = [], set()
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            subscription = str(event.get('subscriptionType') or '')
            prefix, _dot, action = subscription.partition('.')
            object_type = EVENT_OBJECTS.get(prefix if prefix != 'object' else str(event.get('objectTypeId')))
            object_id = event.get('objectId')
            if not object_type or not object_id or object_type not in enabled:
                continue
            direction = 'delete' if action == 'deletion' else 'import'
            key = (object_type, str(object_id), direction)
            if key in seen:
                continue
            seen.add(key)
            values.append({'account_id': account.id, 'object_type': object_type, 'direction': direction,
                           'hubspot_id': str(object_id)})
        if values:
            log = env['hubspot.log'].create({'account_id': account.id, 'direction': 'webhook', 'queued': len(values)})
            pending = env['hubspot.queue'].search([
                ('account_id', '=', account.id), ('state', '=', 'pending'),
                ('hubspot_id', 'in', [v['hubspot_id'] for v in values])])
            known = {(j.object_type, j.hubspot_id, j.direction) for j in pending}
            env['hubspot.queue'].create([dict(v, log_id=log.id) for v in values
                                         if (v['object_type'], v['hubspot_id'], v['direction']) not in known])
        return request.make_json_response({'queued': len(values)})
