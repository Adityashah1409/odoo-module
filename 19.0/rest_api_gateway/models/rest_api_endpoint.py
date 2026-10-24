import json
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

PARAM = re.compile(r'^\{([a-zA-Z_][a-zA-Z0-9_]*)\}$')
SEGMENT = re.compile(r'^[a-zA-Z0-9_.\-]+$')


def json_loads(value):
    return json.loads(value)


def json_dumps(value):
    return json.dumps(value, default=str)


class RestApiEndpoint(models.Model):
    _name = 'rest.api.endpoint'
    _description = 'REST API custom endpoint'
    _order = 'path, method'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    path = fields.Char(
        required=True,
        help='Path below /api/v1/custom/, e.g. "partners/top" or "orders/{id}/lines" ({name} captures a value).')
    method = fields.Selection([
        ('GET', 'GET'), ('POST', 'POST'), ('PUT', 'PUT'), ('PATCH', 'PATCH'), ('DELETE', 'DELETE'),
    ], required=True, default='GET')
    url = fields.Char(compute='_compute_url')
    description = fields.Text(help='Shown in the API documentation.')
    mode = fields.Selection([
        ('domain', 'Records (model + domain)'),
        ('action', 'Server action'),
        ('code', 'Python code'),
    ], required=True, default='domain')
    auth_required = fields.Boolean('Authentication required', default=True)
    run_as = fields.Selection([('caller', 'Caller'), ('sudo', 'Superuser (sudo)')], required=True, default='caller',
                              help='Superuser ignores access rights: only for carefully written endpoints.')
    model_id = fields.Many2one('ir.model', ondelete='cascade')
    model_name = fields.Char(related='model_id.model', string='Model name')
    domain = fields.Char(default='[]',
                         help='Python domain; can use "params" (query/path parameters), e.g. '
                              "[('country_id.code', '=', params.get('country'))]")
    field_ids = fields.Many2many('ir.model.fields', string='Fields',
                                 domain="[('model_id', '=', model_id), ('store', '=', True)]")
    limit = fields.Integer(default=80)
    order = fields.Char()
    action_id = fields.Many2one('ir.actions.server', string='Server action', ondelete='restrict')
    code = fields.Text(
        default="# Available: env, user, params, body, headers, json_dumps, json_loads\n"
                "# Put the JSON answer in `result`.\nresult = {'hello': user.name}\n")
    log_requests = fields.Boolean(default=True)

    _path_method_uniq = models.Constraint('UNIQUE(path, method)', 'An endpoint already uses this path and method.')

    @api.depends('path')
    def _compute_url(self):
        for endpoint in self:
            endpoint.url = f'/api/v1/custom/{endpoint.path}' if endpoint.path else False

    @api.constrains('path', 'mode', 'model_id', 'action_id', 'code', 'run_as', 'auth_required')
    def _check_endpoint(self):
        for endpoint in self:
            segments = (endpoint.path or '').strip('/').split('/')
            if not all(SEGMENT.match(s) or PARAM.match(s) for s in segments):
                raise ValidationError(self.env._(
                    '%s: use letters, digits, "-", "_", "." and {name} placeholders separated by "/".', endpoint.path))
            if endpoint.mode == 'domain' and not endpoint.model_id:
                raise ValidationError(self.env._('%s: choose a model.', endpoint.name))
            if endpoint.mode == 'action' and not endpoint.action_id:
                raise ValidationError(self.env._('%s: choose a server action.', endpoint.name))
            if endpoint.mode == 'code' and not (endpoint.code or '').strip():
                raise ValidationError(self.env._('%s: write the code.', endpoint.name))
            if endpoint.run_as == 'sudo' and not endpoint.auth_required and endpoint.mode != 'domain':
                raise ValidationError(self.env._(
                    '%s: a public endpoint cannot run code or actions as superuser.', endpoint.name))

    @api.onchange('path')
    def _onchange_path(self):
        if self.path:
            self.path = self.path.strip().strip('/')

    # ------------------------------------------------------------------ matching
    @api.model
    def _match(self, subpath, method):
        """Endpoint and captured path parameters for a request, or (empty, None)."""
        parts = subpath.strip('/').split('/')
        for endpoint in self.sudo().search([('method', '=', method)]):
            pattern = endpoint.path.strip('/').split('/')
            if len(pattern) != len(parts):
                continue
            params = {}
            for expected, actual in zip(pattern, parts):
                name = PARAM.match(expected)
                if name:
                    params[name.group(1)] = actual
                elif expected != actual:
                    break
            else:
                return endpoint, params
        return self.browse(), None

    # ------------------------------------------------------------------ running
    def _run(self, env, params, body, headers):
        """Run the endpoint in `env` (caller's or superuser's) and return a JSON-able value."""
        self.ensure_one()
        endpoint = self.sudo()  # configuration is read as superuser, data access runs in `env`
        if endpoint.mode == 'domain':
            domain = safe_eval(endpoint.domain or '[]', {'params': params, 'user': env.user})
            fields_list = endpoint.field_ids.mapped('name') or ['display_name']
            records = env[endpoint.model_name].search(domain, limit=endpoint.limit or None, order=endpoint.order or None)
            return {'count': len(records), 'records': records.read(fields_list)}
        if endpoint.mode == 'action':
            action = env['ir.actions.server'].browse(endpoint.action_id.id)
            ids = params.get('ids')
            if not ids and isinstance(body, dict):
                ids = body.get('ids')
            if isinstance(ids, str):
                ids = [int(i) for i in ids.split(',') if i.strip().isdigit()]
            ctx = {'active_model': action.model_name, 'active_ids': ids or [], 'active_id': (ids or [False])[0],
                   'rest_api_params': params, 'rest_api_body': body}
            return {'result': action.with_context(**ctx).run() or True}
        local = {
            'env': env, 'user': env.user, 'params': params, 'body': body, 'headers': headers,
            'json_dumps': json_dumps, 'json_loads': json_loads, 'result': None,
        }
        safe_eval(endpoint.code, local, mode='exec', filename=f'rest_api_endpoint_{endpoint.id}')
        return local.get('result')

    # ------------------------------------------------------------------ OpenAPI
    @api.model
    def _field_schema(self, field):
        comodel = getattr(field, 'comodel_name', None)  # only relational fields have it in Odoo 20
        mapping = {
            'integer': {'type': 'integer'}, 'float': {'type': 'number'}, 'monetary': {'type': 'number'},
            'boolean': {'type': 'boolean'}, 'date': {'type': 'string', 'format': 'date'},
            'datetime': {'type': 'string', 'format': 'date-time', 'description': 'UTC, "YYYY-MM-DD HH:MM:SS"'},
            'binary': {'type': 'string', 'format': 'byte'},
            'many2one': {'type': 'array', 'items': {}, 'description': f'[id, name] of {comodel}; '
                                                                       'send the id when writing'},
            'one2many': {'type': 'array', 'items': {'type': 'integer'}, 'description': f'ids of {comodel}'},
            'many2many': {'type': 'array', 'items': {'type': 'integer'}, 'description': f'ids of {comodel}'},
        }
        schema = dict(mapping.get(field.type, {'type': 'string'}))
        if field.type == 'selection' and isinstance(field.selection, list):
            schema['enum'] = [key for key, _label in field.selection]
        label = field.string or field.name
        schema['description'] = f"{label}. {schema['description']}" if schema.get('description') else label
        if field.readonly:
            schema['readOnly'] = True
        return schema

    @api.model
    def _openapi(self, base_url):
        ICP = self.env['ir.config_parameter'].sudo()
        doc_models = [m.strip() for m in (ICP.get_param('rest_api_gateway.doc_models', 'res.partner') or '').split(',')
                      if m.strip() in self.env and not self.env[m.strip()]._abstract]
        error = {'$ref': '#/components/responses/Error'}
        model_param = {'name': 'model', 'in': 'path', 'required': True, 'schema': {'type': 'string'},
                       'description': 'Technical model name, e.g. res.partner'}
        id_param = {'name': 'id', 'in': 'path', 'required': True, 'schema': {'type': 'integer'}}
        list_params = [
            {'name': 'domain', 'in': 'query', 'schema': {'type': 'string'}, 'example': '[["is_company", "=", true]]',
             'description': 'Odoo domain as JSON'},
            {'name': 'fields', 'in': 'query', 'schema': {'type': 'string'}, 'example': 'name,email',
             'description': 'Comma-separated fields (default: all readable non-binary fields)'},
            {'name': 'limit', 'in': 'query', 'schema': {'type': 'integer', 'default': 80}},
            {'name': 'offset', 'in': 'query', 'schema': {'type': 'integer', 'default': 0}},
            {'name': 'order', 'in': 'query', 'schema': {'type': 'string'}, 'example': 'name asc'},
            {'name': 'context', 'in': 'query', 'schema': {'type': 'string'}, 'example': '{"lang": "fr_FR"}',
             'description': 'JSON; allowed keys: lang, tz, active_test, allowed_company_ids'},
        ]
        body = {'required': True, 'content': {'application/json': {'schema': {'type': 'object'}}}}

        def op(tag, summary, description='', params=None, request_body=None, ok='OK', public=False, content=None):
            operation = {'tags': [tag], 'summary': summary, 'description': description,
                         'parameters': params or [],
                         'responses': {'200': {'description': ok, 'content': content or {
                             'application/json': {'schema': {'type': 'object'}}}},
                             '400': error, '401': error, '403': error, '404': error, '429': error}}
            if request_body:
                operation['requestBody'] = request_body
            if public:
                operation['security'] = []
            return operation

        paths = {
            '/ping': {'get': op('Server', 'Health check', public=True)},
            '/me': {'get': op('Server', 'Server version, database, current user and company')},
            '/oauth2/token': {'post': op(
                'Authentication', 'Get an access token (OAuth2 client credentials)',
                'Send grant_type=client_credentials with client_id and client_secret (form, JSON or HTTP Basic).',
                request_body={'required': True, 'content': {'application/x-www-form-urlencoded': {'schema': {
                    'type': 'object', 'properties': {'grant_type': {'type': 'string', 'enum': ['client_credentials']},
                                                     'client_id': {'type': 'string'},
                                                     'client_secret': {'type': 'string'}}}}}},
                public=True)},
            '/oauth2/revoke': {'post': op('Authentication', 'Revoke an access token', public=True,
                                          request_body=body)},
            '/{model}': {
                'get': op('Records', 'Search records', 'Returns {count, limit, offset, records}.',
                          [model_param, *list_params]),
                'post': op('Records', 'Create a record (or a list of records)', 'Returns {id} or {ids} (201).',
                           [model_param], body, ok='Created'),
            },
            '/{model}/{id}': {
                'get': op('Records', 'Read a record', params=[model_param, id_param, list_params[1], list_params[5]]),
                'put': op('Records', 'Update a record', params=[model_param, id_param], request_body=body),
                'patch': op('Records', 'Update a record', params=[model_param, id_param], request_body=body),
                'delete': op('Records', 'Delete a record', params=[model_param, id_param]),
            },
            '/{model}/call/{method}': {'post': op(
                'Methods', 'Call a public model method',
                'Body: {"ids": [1, 2], "args": [...], "kwargs": {...}}. Leave "ids" out for model methods. '
                'Private methods (starting with "_") cannot be called.',
                [model_param, {'name': 'method', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                body)},
            '/{model}/{id}/{field}/download': {'get': op(
                'Files', 'Download a binary field', params=[model_param, id_param, {
                    'name': 'field', 'in': 'path', 'required': True, 'schema': {'type': 'string'}}],
                content={'application/octet-stream': {'schema': {'type': 'string', 'format': 'binary'}}})},
            '/report/{report}/{ids}': {'get': op(
                'Files', 'Print a report', 'report: technical name or XML ID; ids: comma-separated.',
                [{'name': 'report', 'in': 'path', 'required': True, 'schema': {'type': 'string'},
                  'example': 'base.report_irmodulereference'},
                 {'name': 'ids', 'in': 'path', 'required': True, 'schema': {'type': 'string'}, 'example': '1,2'},
                 {'name': 'format', 'in': 'query', 'schema': {'type': 'string', 'enum': ['pdf', 'html']}}],
                content={'application/pdf': {'schema': {'type': 'string', 'format': 'binary'}}})},
        }
        schemas = {'Error': {'type': 'object', 'properties': {'error': {'type': 'object', 'properties': {
            'code': {'type': 'string'}, 'message': {'type': 'string'}, 'status': {'type': 'integer'}}}}}}
        for model_name in doc_models:
            Model = self.env[model_name]
            schema_name = model_name.replace('.', '_')
            schemas[schema_name] = {
                'type': 'object', 'description': Model._description,
                'properties': {name: self._field_schema(field) for name, field in sorted(Model._fields.items())
                               if field.store or name in ('id', 'display_name')},
            }
            ref = {'application/json': {'schema': {'$ref': f'#/components/schemas/{schema_name}'}}}
            paths[f'/{model_name}'] = {
                'get': op(model_name, f'Search {Model._description}', params=list_params),
                'post': op(model_name, f'Create a {Model._description}', request_body={'required': True,
                                                                                    'content': ref}, ok='Created'),
            }
            paths[f'/{model_name}/{{id}}'] = {
                'get': op(model_name, f'Read a {Model._description}', params=[id_param], content=ref),
                'put': op(model_name, f'Update a {Model._description}', params=[id_param],
                          request_body={'required': True, 'content': ref}),
                'delete': op(model_name, f'Delete a {Model._description}', params=[id_param]),
            }
        for endpoint in self.search([]):
            names = [m.group(1) for m in (PARAM.match(s) for s in endpoint.path.split('/')) if m]
            paths.setdefault(f'/custom/{endpoint.path}', {})[endpoint.method.lower()] = op(
                'Custom endpoints', endpoint.name, endpoint.description or '',
                [{'name': n, 'in': 'path', 'required': True, 'schema': {'type': 'string'}} for n in names],
                request_body=body if endpoint.method in ('POST', 'PUT', 'PATCH') else None,
                public=not endpoint.auth_required)
        # anonymous docs requests have no user, hence no current company
        company = self.env.company or self.env['res.company'].sudo().search([], limit=1)
        return {
            'openapi': '3.0.3',
            'info': {
                'title': f'{company.name} REST API', 'version': '1.0',
                'description': 'JSON API of this Odoo database. Every call runs with the access rights of the '
                               'authenticated user. Authenticate with Basic (login + password or API key), '
                               'a Bearer API key, or a Bearer OAuth2 access token. On a server hosting several '
                               f'databases, add the header "X-Odoo-Database: {self.env.cr.dbname}".',
            },
            'servers': [{'url': f'{base_url}/api/v1'}],
            'security': [{'basicAuth': []}, {'bearerAuth': []}, {'oauth2': []}],
            'tags': [{'name': name} for name in ['Server', 'Authentication', 'Records', 'Methods', 'Files',
                                                  'Custom endpoints', *doc_models]],
            'paths': paths,
            'components': {
                'securitySchemes': {
                    'basicAuth': {'type': 'http', 'scheme': 'basic', 'description': 'Login and password or API key'},
                    'bearerAuth': {'type': 'http', 'scheme': 'bearer',
                                   'description': 'Odoo API key or OAuth2 access token'},
                    'oauth2': {'type': 'oauth2', 'flows': {'clientCredentials': {
                        'tokenUrl': f'{base_url}/api/v1/oauth2/token', 'scopes': {}}}},
                },
                'responses': {'Error': {'description': 'Error', 'content': {
                    'application/json': {'schema': {'$ref': '#/components/schemas/Error'}}}}},
                'schemas': schemas,
            },
        }
