import hmac
import logging

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

_logger = logging.getLogger(__name__)


class PowerBIFeed(http.Controller):
    """JSON feed for Power BI Desktop / Service (Get data › Web).

    Authentication: header ``X-API-Key: <dataset key>`` (or ``?key=`` for quick tests).
    Data is read with the dataset's "Read data as" user, so record rules apply.
    """

    def _dataset(self, dataset_id, key):
        dataset = request.env['powerbi.dataset'].sudo().browse(dataset_id).exists()
        if not dataset or not dataset.active or dataset.mode != 'feed' or not key \
                or not hmac.compare_digest(dataset.access_key or '', key):
            return None
        return dataset

    def _key(self, kwargs):
        return request.httprequest.headers.get('X-API-Key') or kwargs.get('key')

    @http.route('/powerbi/feed/<int:dataset_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def feed_index(self, dataset_id, **kwargs):
        dataset = self._dataset(dataset_id, self._key(kwargs))
        if not dataset:
            return request.make_json_response({'error': 'invalid dataset or key'}, status=403)
        base = request.httprequest.host_url.rstrip('/')
        return request.make_json_response({
            'dataset': dataset.name,
            'tables': [{'name': t.name, 'url': f"{base}/powerbi/feed/{dataset.id}/{t.name}",
                        'columns': t._schema()['columns']} for t in dataset.table_ids],
            'relationships': dataset._relationships(),
        })

    @http.route('/powerbi/feed/<int:dataset_id>/<string:table_name>', type='http', auth='public',
                methods=['GET'], csrf=False)
    def feed_table(self, dataset_id, table_name, **kwargs):
        dataset = self._dataset(dataset_id, self._key(kwargs))
        if not dataset:
            return request.make_json_response({'error': 'invalid dataset or key'}, status=403)
        table = dataset.table_ids.filtered(lambda t: t.name == table_name)
        if not table:
            return request.make_json_response({'error': 'unknown table'}, status=404)
        try:
            rows = table._rows(table._records())
        except AccessError:
            _logger.warning("Power BI feed: user %s cannot read %s", dataset.user_id.login, table.model_name)
            return request.make_json_response({'error': 'access denied for the feed user'}, status=403)
        dataset._log('feed', f"{len(rows)} row(s) served for {table.name}", rows=len(rows), table=table)
        return request.make_json_response(rows)
