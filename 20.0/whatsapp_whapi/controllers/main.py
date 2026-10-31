import json
import logging

from odoo import http
from odoo.http import request
from odoo.tools import consteq

_logger = logging.getLogger(__name__)


class WhapiWebhook(http.Controller):

    @http.route('/whapi/webhook/<int:account_id>/<string:secret>', type='http', auth='public', methods=['POST'],
                csrf=False, save_session=False)
    def whapi_webhook(self, account_id, secret, **kw):
        account = request.env['whapi.account'].sudo().browse(account_id).exists()
        if not account or not account.active or not account.webhook_secret \
                or not consteq(account.webhook_secret, secret):
            _logger.warning('Whapi webhook refused for account %s', account_id)
            return request.make_json_response({'error': 'forbidden'}, status=403)
        try:
            payload = json.loads(request.httprequest.get_data() or b'{}')
        except ValueError:
            return request.make_json_response({'error': 'invalid json'}, status=400)
        if not isinstance(payload, dict):
            return request.make_json_response({'error': 'invalid payload'}, status=400)
        result = account.with_company(account.company_id)._whapi_process_webhook(payload)
        return request.make_json_response(dict(result, ok=True))
