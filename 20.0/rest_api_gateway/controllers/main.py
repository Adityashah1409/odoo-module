import base64
import json
import logging
import time
from datetime import date, datetime
from urllib.parse import urlencode

from psycopg2 import IntegrityError

from markupsafe import Markup
from werkzeug.exceptions import NotFound

from odoo import fields, http, models, release
from odoo.exceptions import AccessDenied, AccessError, MissingError, UserError, ValidationError
from odoo.http import request
from odoo.service.model import call_kw
from odoo.tools.mimetypes import guess_mimetype

_logger = logging.getLogger(__name__)

PREFIX = '/api/v1'
ALL_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
READ_METHODS = {'read', 'search', 'search_read', 'search_count', 'read_group', 'name_search', 'fields_get',
                'default_get', 'check_access_rights', 'has_group', 'web_search_read', 'web_read', 'formatted_read_group'}
CONTEXT_KEYS = {'lang', 'tz', 'active_test', 'allowed_company_ids'}


class Result:
    """Handler answer with an explicit status and, for custom endpoints, the endpoint used."""

    def __init__(self, value, status=200, endpoint=None):
        self.value, self.status, self.endpoint = value, status, endpoint


class ApiError(Exception):
    def __init__(self, status, message, code=None, headers=None):
        super().__init__(message)
        self.status, self.message, self.code, self.headers = status, message, code, headers or {}


def json_default(value):
    if isinstance(value, datetime):
        return fields.Datetime.to_string(value)
    if isinstance(value, date):
        return fields.Date.to_string(value)
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(value).decode()
    if isinstance(value, models.BaseModel):
        return value.ids
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    if isinstance(value, Markup):
        return str(value)
    if hasattr(value, '__bytes__'):  # Odoo 20 binary values
        return base64.b64encode(bytes(value)).decode()
    return str(value)


def dumps(value):
    return json.dumps(value, default=json_default, ensure_ascii=False)


class RestApi(http.Controller):

    # ------------------------------------------------------------------ plumbing
    def _json(self, value, status=200):
        return request.make_response(dumps(value), status=status,
                                     headers=[('Content-Type', 'application/json; charset=utf-8')])

    def _cors(self, response):
        origins = request.env['ir.config_parameter'].sudo().get_str('rest_api_gateway.cors_origins') or ''
        allowed = [o.strip() for o in origins.split(',') if o.strip()]
        origin = request.httprequest.headers.get('Origin')
        if origin and ('*' in allowed or origin in allowed):
            response.headers['Access-Control-Allow-Origin'] = '*' if '*' in allowed else origin
            response.headers['Access-Control-Allow-Methods'] = ', '.join(ALL_METHODS)
            response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, X-Odoo-Database'
            response.headers['Access-Control-Max-Age'] = '600'
            if '*' not in allowed:
                response.headers['Vary'] = 'Origin'
        return response

    @staticmethod
    def _is_form():
        content_type = request.httprequest.content_type or ''
        return 'application/x-www-form-urlencoded' in content_type or 'multipart/form-data' in content_type

    def _raw_body(self):
        """Body as text (form bodies are parsed by werkzeug first, then re-encoded)."""
        if self._is_form():
            return urlencode(list(request.httprequest.form.items(multi=True)))
        return request.httprequest.get_data(as_text=True)

    def _body(self):
        if self._is_form():
            return dict(request.httprequest.form)
        raw = request.httprequest.get_data(as_text=True)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except ValueError:
            raise ApiError(400, 'The request body is not valid JSON.', 'invalid_json') from None

    @staticmethod
    def _json_param(name, default=None):
        value = request.httprequest.args.get(name)
        if value in (None, ''):
            return default
        try:
            return json.loads(value)
        except ValueError:
            raise ApiError(400, f'Parameter "{name}" must be JSON.', 'invalid_parameter') from None

    @staticmethod
    def _int_param(name, default):
        value = request.httprequest.args.get(name)
        if value in (None, ''):
            return default
        try:
            return int(value)
        except ValueError:
            raise ApiError(400, f'Parameter "{name}" must be an integer.', 'invalid_parameter') from None

    def _authenticate(self):
        """Return the rest.api.client used (or an empty recordset) and switch the request to the user."""
        header = request.httprequest.headers.get('Authorization', '')
        scheme, _sep, value = header.partition(' ')
        scheme, value = scheme.lower(), value.strip()
        env = request.env(su=True)
        client = env['rest.api.client']
        uid = None
        if scheme == 'bearer' and value:
            token = env['rest.api.token']._find(value)
            if token:
                client = token.client_id
                uid = client.user_id.id
            else:
                uid = env['res.users.apikeys']._check_credentials(scope='rpc', key=value)
            if not uid:
                raise ApiError(401, 'Invalid or expired token.', 'invalid_token',
                               {'WWW-Authenticate': 'Bearer error="invalid_token"'})
        elif scheme == 'basic' and value:
            try:
                login, _sep, secret = base64.b64decode(value).decode().partition(':')
            except (ValueError, UnicodeDecodeError):
                raise ApiError(401, 'Malformed Basic credentials.', 'invalid_credentials') from None
            try:
                info = env['res.users'].authenticate(
                    {'type': 'password', 'login': login, 'password': secret}, {'interactive': False})
            except AccessDenied:
                raise ApiError(401, 'Wrong login, password or API key.', 'invalid_credentials',
                               {'WWW-Authenticate': 'Basic realm="Odoo API"'}) from None
            uid = info['uid']
        else:
            raise ApiError(401, 'Authentication required: Basic (login + password or API key) or Bearer token.',
                           'unauthenticated', {'WWW-Authenticate': 'Basic realm="Odoo API", Bearer'})
        user = env['res.users'].browse(uid)
        if not user.active or user._is_public():
            raise ApiError(401, 'This user cannot use the API.', 'invalid_user')
        request.update_env(user=uid, context=env['res.users'].with_user(uid).context_get())
        return client

    def _rate_limit(self, ip):
        limit = (request.env['ir.config_parameter'].sudo().get_int('rest_api_gateway.rate_limit', 0) or 0)
        if limit and request.env['rest.api.log']._recent_count(request.env.uid, ip) >= limit:
            raise ApiError(429, f'Rate limit reached ({limit} requests per minute).', 'rate_limited',
                           {'Retry-After': '60'})

    def _handle(self, handler, *, auth=True, log=True):
        """Run `handler(client)` with authentication, error mapping, CORS, rate limit and logging."""
        http_request = request.httprequest
        if http_request.method == 'OPTIONS':
            return self._cors(request.make_response('', status=204))
        started = time.monotonic()
        ip = http_request.remote_addr
        client = request.env['rest.api.client']
        endpoint = None
        response_text = ''
        error = None
        try:
            if auth:
                client = self._authenticate()
                self._rate_limit(ip)
            result = handler(client)
            status = 200
            if isinstance(result, Result):
                result, status, endpoint = result.value, result.status, result.endpoint
            if isinstance(result, http.Response) or hasattr(result, 'status_code'):
                response = result
            else:
                response_text = dumps(result)
                response = request.make_response(response_text, status=status,
                                                 headers=[('Content-Type', 'application/json; charset=utf-8')])
        except Exception as e:  # noqa: BLE001 - every error becomes a JSON answer
            request.env.cr.rollback()
            status, code, message, headers = self._map_error(e)
            error = message
            response_text = dumps({'error': {'code': code, 'message': message, 'status': status}})
            response = request.make_response(response_text, status=status,
                                             headers=[('Content-Type', 'application/json; charset=utf-8'),
                                                      *headers.items()])
        if log and (endpoint is None or endpoint.log_requests):
            try:
                request.env['rest.api.log']._record({
                    'method': http_request.method, 'path': http_request.path[:500],
                    'query': http_request.query_string.decode()[:500], 'status': response.status_code,
                    'duration_ms': int((time.monotonic() - started) * 1000),
                    'user_id': request.env.uid if request.env.uid and not request.env.user._is_public() else False,
                    'client_id': client.id, 'endpoint_id': endpoint.id if endpoint else False, 'ip': ip,
                    'user_agent': (http_request.user_agent.string or '')[:300], 'error': error,
                }, request_body=self._raw_body(), response_body=response_text)
            except Exception:  # noqa: BLE001 - never fail a request because of its log
                _logger.exception('REST API: could not log the request')
        return self._cors(response)

    @staticmethod
    def _map_error(e):
        if isinstance(e, ApiError):
            return e.status, e.code or 'error', e.message, e.headers
        if isinstance(e, AccessDenied):
            return 401, 'access_denied', 'Access denied.', {}
        if isinstance(e, MissingError):
            return 404, 'not_found', str(e.args[0] if e.args else e), {}
        if isinstance(e, AccessError):
            return 403, 'forbidden', str(e.args[0] if e.args else e), {}
        if isinstance(e, (UserError, ValidationError)):
            return 400, 'validation_error', str(e.args[0] if e.args else e), {}
        if isinstance(e, IntegrityError):
            diag = getattr(e, 'diag', None)
            detail = (diag and (diag.message_primary or diag.constraint_name)) or 'constraint violated'
            return 400, 'integrity_error', f'Database constraint: {detail}.', {}
        if isinstance(e, NotFound):
            return 404, 'not_found', 'Not found.', {}
        if isinstance(e, (ValueError, TypeError, KeyError, AttributeError)):
            return 400, 'bad_request', str(e), {}
        _logger.exception('REST API: unexpected error')
        return 500, 'server_error', 'Internal server error.', {}

    def _model(self, client, model_name, write=False):
        env = request.env
        if model_name not in env or env[model_name]._abstract:
            raise ApiError(404, f'Unknown model "{model_name}".', 'unknown_model')
        if client and not client._allows(model_name, write):
            raise ApiError(403, f'This client may not {"change" if write else "read"} "{model_name}".', 'forbidden')
        return env[model_name]

    def _context(self, Model):
        context = self._json_param('context', {}) or {}
        if not isinstance(context, dict):
            raise ApiError(400, 'Parameter "context" must be a JSON object.', 'invalid_parameter')
        return Model.with_context(**{k: v for k, v in context.items() if k in CONTEXT_KEYS})

    def _fields(self, Model):
        value = request.httprequest.args.get('fields')
        if value:
            names = json.loads(value) if value.startswith('[') else [f.strip() for f in value.split(',') if f.strip()]
            unknown = [name for name in names if name not in Model._fields]
            if unknown:
                raise ApiError(400, f'Unknown field(s): {", ".join(unknown)}.', 'unknown_field')
            return names
        # by default, every field the user may read (fields_get skips restricted ones) except binaries
        return [name for name, desc in Model.fields_get(attributes=['type']).items() if desc['type'] != 'binary']

    # ------------------------------------------------------------------ info and auth
    @http.route(f'{PREFIX}/ping', type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False, save_session=False, readonly=False)
    def ping(self, **kwargs):
        return self._handle(lambda client: {'status': 'ok', 'time': fields.Datetime.now()}, auth=False, log=False)

    @http.route([PREFIX, f'{PREFIX}/me'], type='http', auth='none', methods=['GET', 'OPTIONS'], csrf=False,
                save_session=False, readonly=False)
    def info(self, **kwargs):
        def handler(client):
            user = request.env.user
            return {
                'server_version': release.version,
                'database': request.db,
                'user': {'id': user.id, 'name': user.name, 'login': user.login, 'lang': user.lang, 'tz': user.tz},
                'company': {'id': user.company_id.id, 'name': user.company_id.name},
                'client': client.name if client else None,
            }
        return self._handle(handler)

    @http.route(f'{PREFIX}/oauth2/token', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False,
                save_session=False, readonly=False)
    def oauth2_token(self, **kwargs):
        def handler(_client):
            body = self._body()
            client_id, secret = body.get('client_id'), body.get('client_secret')
            header = request.httprequest.headers.get('Authorization', '')
            if header.lower().startswith('basic '):
                try:
                    client_id, _sep, secret = base64.b64decode(header[6:].strip()).decode().partition(':')
                except (ValueError, UnicodeDecodeError):
                    raise ApiError(401, 'Malformed client credentials.', 'invalid_client') from None
            if body.get('grant_type') != 'client_credentials':
                raise ApiError(400, 'Only grant_type=client_credentials is supported.', 'unsupported_grant_type')
            client = request.env['rest.api.client'].sudo().search([('client_id', '=', client_id or '')], limit=1)
            if not client or not client._check_secret(secret):
                raise ApiError(401, 'Unknown client or wrong secret.', 'invalid_client')
            token, lifetime = client._issue_token()
            return {'access_token': token, 'token_type': 'Bearer', 'expires_in': lifetime}
        return self._handle(handler, auth=False)

    @http.route(f'{PREFIX}/oauth2/revoke', type='http', auth='none', methods=['POST', 'OPTIONS'], csrf=False,
                save_session=False, readonly=False)
    def oauth2_revoke(self, **kwargs):
        def handler(_client):
            token = request.env['rest.api.token']._find(self._body().get('token'))
            token.sudo().unlink()
            return {'revoked': True}
        return self._handle(handler, auth=False)

    # ------------------------------------------------------------------ records
    @http.route(f'{PREFIX}/<string:model>', type='http', auth='none', methods=['GET', 'POST', 'OPTIONS'],
                csrf=False, save_session=False, readonly=False)
    def collection(self, model, **kwargs):
        def handler(client):
            if request.httprequest.method == 'POST':
                Model = self._context(self._model(client, model, write=True))
                values = self._body()
                if isinstance(values, list):
                    return Result({'ids': Model.create(values).ids}, 201)
                if not isinstance(values, dict):
                    raise ApiError(400, 'Send a JSON object (or a list of objects).', 'invalid_body')
                return Result({'id': Model.create(values).id}, 201)
            Model = self._context(self._model(client, model))
            domain = self._json_param('domain', []) or []
            max_limit = (request.env['ir.config_parameter'].sudo().get_int('rest_api_gateway.max_limit', 1000)
                            or 1000)
            limit = min(self._int_param('limit', 80), max_limit)
            offset = self._int_param('offset', 0)
            order = request.httprequest.args.get('order') or None
            records = Model.search(domain, limit=limit, offset=offset, order=order)
            return {
                'count': Model.search_count(domain),
                'limit': limit, 'offset': offset,
                'records': records.read(self._fields(Model)),
            }
        return self._handle(handler)

    @http.route(f'{PREFIX}/<string:model>/<int:rec_id>', type='http', auth='none',
                methods=['GET', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'], csrf=False, save_session=False, readonly=False)
    def record(self, model, rec_id, **kwargs):
        def handler(client):
            method = request.httprequest.method
            Model = self._context(self._model(client, model, write=method != 'GET'))
            record = Model.browse(rec_id).exists()
            if not record:
                raise ApiError(404, f'{model} {rec_id} does not exist.', 'not_found')
            if method == 'GET':
                return record.read(self._fields(Model))[0]
            if method == 'DELETE':
                record.unlink()
                return {'id': rec_id, 'deleted': True}
            values = self._body()
            if not isinstance(values, dict):
                raise ApiError(400, 'Send a JSON object with the fields to change.', 'invalid_body')
            record.write(values)
            return {'id': rec_id, 'updated': True}
        return self._handle(handler)

    @http.route(f'{PREFIX}/<string:model>/call/<string:method>', type='http', auth='none',
                methods=['POST', 'OPTIONS'], csrf=False, save_session=False, readonly=False)
    def call(self, model, method, **kwargs):
        def handler(client):
            Model = self._context(self._model(client, model, write=method not in READ_METHODS))
            body = self._body()
            if not isinstance(body, dict):
                raise ApiError(400, 'Send {"ids": [...], "args": [...], "kwargs": {...}}.', 'invalid_body')
            args = list(body.get('args') or [])
            if 'ids' in body:
                args.insert(0, body['ids'])
            return {'result': call_kw(Model, method, args, body.get('kwargs') or {})}
        return self._handle(handler)

    @http.route(f'{PREFIX}/<string:model>/<int:rec_id>/<string:field>/download', type='http', auth='none',
                methods=['GET', 'OPTIONS'], csrf=False, save_session=False, readonly=False)
    def download(self, model, rec_id, field, **kwargs):
        def handler(client):
            Model = self._model(client, model)
            if Model._fields.get(field) is None or Model._fields[field].type != 'binary':
                raise ApiError(400, f'"{field}" is not a binary field of {model}.', 'invalid_field')
            record = Model.browse(rec_id).exists()
            if not record:
                raise ApiError(404, f'{model} {rec_id} does not exist.', 'not_found')
            value = record[field]
            if not value:
                raise ApiError(404, 'This field is empty.', 'empty')
            data = base64.b64decode(value) if isinstance(value, (bytes, str)) else bytes(value)
            mimetype = guess_mimetype(data, default='application/octet-stream')
            return request.make_response(data, headers=[('Content-Type', mimetype),
                                                        ('Content-Length', str(len(data)))])
        return self._handle(handler)

    @http.route(f'{PREFIX}/report/<string:report>/<string:ids>', type='http', auth='none',
                methods=['GET', 'OPTIONS'], csrf=False, save_session=False, readonly=False)
    def report(self, report, ids, **kwargs):
        def handler(client):
            Report = request.env['ir.actions.report']
            action = Report.sudo().search([('report_name', '=', report)], limit=1)
            if not action:
                action = request.env.ref(report, raise_if_not_found=False)
            if not action or action._name != 'ir.actions.report':
                raise ApiError(404, f'Unknown report "{report}".', 'unknown_report')
            record_ids = [int(i) for i in ids.split(',') if i.strip().isdigit()]
            records = self._model(client, action.model).browse(record_ids).exists()
            if not records:
                raise ApiError(404, 'No record to print.', 'not_found')
            records.check_access('read')
            fmt = request.httprequest.args.get('format', 'pdf')
            if fmt == 'html':
                content, _type = Report._render_qweb_html(action.report_name, records.ids)
                return request.make_response(content, headers=[('Content-Type', 'text/html; charset=utf-8')])
            if fmt != 'pdf':
                raise ApiError(400, 'format must be pdf or html.', 'invalid_parameter')
            content, _type = Report._render_qweb_pdf(action.report_name, records.ids)
            return request.make_response(content, headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'inline; filename="{report.replace(".", "_")}.pdf"')])
        return self._handle(handler)

    # ------------------------------------------------------------------ custom endpoints
    @http.route(f'{PREFIX}/custom/<path:subpath>', type='http', auth='none', methods=ALL_METHODS, csrf=False,
                save_session=False, readonly=False)
    def custom(self, subpath, **kwargs):
        method = request.httprequest.method
        endpoint, path_params = request.env['rest.api.endpoint']._match(subpath, method)
        if not endpoint:
            if method == 'OPTIONS':
                return self._cors(request.make_response('', status=204))
            return self._handle(self._not_found, auth=False)

        def handler(client):
            if not endpoint.auth_required:
                request.update_env(user=request.env.ref('base.public_user').id)
            params = dict(request.httprequest.args, **path_params)
            body = self._body() if method != 'GET' else {}
            headers = {k: v for k, v in request.httprequest.headers.items() if k.lower() != 'authorization'}
            env = request.env(su=True) if endpoint.run_as == 'sudo' else request.env
            return Result(endpoint.sudo()._run(env, params, body, headers), endpoint=endpoint)
        return self._handle(handler, auth=endpoint.auth_required, log=endpoint.log_requests)

    @staticmethod
    def _not_found(_client):
        raise ApiError(404, 'No such endpoint.', 'not_found')

    # ------------------------------------------------------------------ documentation
    def _docs_allowed(self):
        if request.env['ir.config_parameter'].sudo().get_bool('rest_api_gateway.docs_public'):
            return True
        return bool(request.session.uid)

    @http.route(f'{PREFIX}/openapi.json', type='http', auth='none', methods=['GET'], csrf=False, readonly=False)
    def openapi(self, **kwargs):
        if not self._docs_allowed():
            return self._json({'error': {'code': 'unauthenticated', 'message': 'Log in to Odoo to read the docs.'}},
                              status=401)
        spec = request.env['rest.api.endpoint'].sudo()._openapi(request.httprequest.host_url.rstrip('/'))
        return self._cors(self._json(spec))

    @http.route('/api/docs', type='http', auth='none', methods=['GET'], csrf=False, readonly=False)
    def docs(self, **kwargs):
        if not self._docs_allowed():
            return request.redirect('/web/login?redirect=/api/docs')
        return request.render('rest_api_gateway.api_docs', {'spec_url': f'{PREFIX}/openapi.json', 'db': request.db})
