import base64

from odoo.exceptions import ValidationError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')


@tagged('post_install', '-at_install')
class TestRestApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.ICP.set_int('rest_api_gateway.rate_limit', 0)
        cls.user = new_test_user(cls.env, login='api_user', password='api_user_pwd_123',
                                 groups='base.group_user,base.group_partner_manager', name='Api User')
        cls.key = cls.env['res.users.apikeys'].with_user(cls.user).sudo()._generate('rpc', 'tests', None)
        cls.admin_key = cls.env['res.users.apikeys'].with_user(cls.env.ref('base.user_admin')).sudo()._generate(
            'rpc', 'tests', None)
        cls.partner = cls.env['res.partner'].create({'name': 'API Partner', 'email': 'api@example.com'})

    def api(self, method, path, body=None, key=None, headers=None, raw=None):
        all_headers = {'Authorization': f'Bearer {key or self.key}'} if key is not False else {}
        all_headers.update(headers or {})
        if raw is not None:
            return self.url_open(f'/api/v1{path}', data=raw, headers=all_headers, method=method)
        return self.url_open(f'/api/v1{path}', json=body, headers=all_headers, method=method)

    # ------------------------------------------------------------------ auth
    def test_ping_and_authentication(self):
        self.assertEqual(self.api('GET', '/ping', key=False).json()['status'], 'ok')
        response = self.api('GET', '/me', key=False)
        self.assertEqual(response.status_code, 401)
        self.assertIn('WWW-Authenticate', response.headers)
        self.assertEqual(self.api('GET', '/me', key='wrong').status_code, 401)
        self.assertEqual(self.api('GET', '/me').json()['user']['login'], 'api_user')
        for secret in ('api_user_pwd_123', self.key):
            basic = base64.b64encode(f'api_user:{secret}'.encode()).decode()
            response = self.api('GET', '/me', key=False, headers={'Authorization': f'Basic {basic}'})
            self.assertEqual(response.status_code, 200, secret)
        basic = base64.b64encode(b'api_user:nope').decode()
        self.assertEqual(self.api('GET', '/me', key=False, headers={'Authorization': f'Basic {basic}'}).status_code, 401)

    # ------------------------------------------------------------------ records
    def test_crud(self):
        response = self.api('POST', '/res.partner', {'name': 'Created by API', 'email': 'new@example.com'})
        self.assertEqual(response.status_code, 201)
        new_id = response.json()['id']
        data = self.api('GET', f'/res.partner?domain=[["id","=",{new_id}]]&fields=name,email').json()
        self.assertEqual((data['count'], data['records'][0]['email']), (1, 'new@example.com'))
        self.assertEqual(set(data['records'][0]), {'id', 'name', 'email'})
        record = self.api('GET', f'/res.partner/{new_id}').json()
        self.assertEqual(record['name'], 'Created by API')
        self.assertNotIn('image_1920', record, 'binary fields are not read by default')
        self.assertEqual(self.api('PUT', f'/res.partner/{new_id}', {'city': 'Lyon'}).json()['updated'], True)
        self.assertEqual(self.env['res.partner'].browse(new_id).city, 'Lyon')
        self.assertEqual(self.api('DELETE', f'/res.partner/{new_id}').json()['deleted'], True)
        self.assertEqual(self.api('GET', f'/res.partner/{new_id}').status_code, 404)
        ids = self.api('POST', '/res.partner', [{'name': 'Batch 1'}, {'name': 'Batch 2'}]).json()['ids']
        self.assertEqual(len(ids), 2)

    def test_access_rights_and_errors(self):
        # the user's rights apply: no access to system parameters
        response = self.api('GET', '/ir.config_parameter')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 'forbidden')
        self.assertEqual(self.api('GET', '/no.such.model').status_code, 404)
        self.assertEqual(self.api('GET', '/res.partner?domain=notjson').status_code, 400)
        self.assertEqual(self.api('GET', '/res.partner?fields=name,unknown_field').status_code, 400)
        self.assertEqual(self.api('POST', '/res.partner', raw='{broken', headers={
            'Content-Type': 'application/json'}).json()['error']['code'], 'invalid_json')
        with mute_logger('odoo.sql_db'):
            response = self.api('POST', '/res.partner', {'name': False})
        self.assertEqual((response.status_code, response.json()['error']['code']), (400, 'integrity_error'))
        # failed requests are rolled back and logged
        self.assertTrue(self.env['rest.api.log'].search([('status', '=', 403), ('user_id', '=', self.user.id)]))

    def test_call_method(self):
        result = self.api('POST', '/res.partner/call/name_search', {'kwargs': {'name': 'API Partner'}}).json()
        self.assertIn(self.partner.id, [r[0] for r in result['result']])
        result = self.api('POST', '/res.partner/call/read', {'ids': [self.partner.id], 'args': [['email']]}).json()
        self.assertEqual(result['result'][0]['email'], 'api@example.com')
        self.assertEqual(self.api('POST', '/res.partner/call/_compute_display_name', {'ids': [self.partner.id]})
                         .status_code, 403)

    # ------------------------------------------------------------------ OAuth2
    def test_oauth2_client_credentials(self):
        client = self.env['rest.api.client'].create({'name': 'Scanner', 'user_id': self.user.id,
                                                     'model_ids': [(6, 0, self.env['ir.model']._get('res.partner').ids)]})
        secret = self.env['rest.api.secret.wizard'].browse(client.action_generate_secret()['res_id']).secret
        self.assertNotEqual(client.sudo().secret_hash, secret, 'only the hash is stored')
        bad = self.url_open('/api/v1/oauth2/token', data={'grant_type': 'client_credentials',
                                                          'client_id': client.client_id, 'client_secret': 'x'})
        self.assertEqual((bad.status_code, bad.json()['error']['code']), (401, 'invalid_client'))
        unsupported = self.url_open('/api/v1/oauth2/token', data={'grant_type': 'password'})
        self.assertEqual(unsupported.json()['error']['code'], 'unsupported_grant_type')
        token = self.url_open('/api/v1/oauth2/token', data={
            'grant_type': 'client_credentials', 'client_id': client.client_id, 'client_secret': secret}).json()
        self.assertEqual(token['token_type'], 'Bearer')
        me = self.api('GET', '/me', key=token['access_token']).json()
        self.assertEqual((me['client'], me['user']['login']), ('Scanner', 'api_user'))
        # allowed models and read-only
        self.assertEqual(self.api('GET', '/res.users', key=token['access_token']).status_code, 403)
        client.read_only = True
        self.assertEqual(self.api('POST', '/res.partner', {'name': 'x'}, key=token['access_token']).status_code, 403)
        self.assertEqual(self.api('GET', '/res.partner', key=token['access_token']).status_code, 200)
        # revoke
        self.url_open('/api/v1/oauth2/revoke', json={'token': token['access_token']})
        self.assertEqual(self.api('GET', '/me', key=token['access_token']).status_code, 401)

    # ------------------------------------------------------------------ custom endpoints
    def test_custom_endpoints(self):
        Endpoint = self.env['rest.api.endpoint']
        partner_model = self.env['ir.model']._get('res.partner')
        Endpoint.create({
            'name': 'Partners by email domain', 'path': 'partners/{domain}', 'mode': 'domain',
            'model_id': partner_model.id, 'domain': "[('email', '=ilike', '%@' + params['domain'])]",
            'field_ids': [(6, 0, self.env['ir.model.fields']._get('res.partner', 'email').ids)],
        })
        Endpoint.create({'name': 'Echo', 'path': 'echo', 'method': 'POST', 'mode': 'code',
                         'code': "result = {'you_sent': body, 'user': user.login, 'q': params.get('q')}"})
        action = self.env['ir.actions.server'].create({
            'name': 'Tag as API', 'model_id': partner_model.id, 'state': 'code',
            'code': "records.write({'comment': 'touched by the API'})"})
        Endpoint.create({'name': 'Touch', 'path': 'touch', 'method': 'POST', 'mode': 'action',
                         'action_id': action.id})
        data = self.api('GET', '/custom/partners/example.com').json()
        emails = [r['email'] for r in data['records']]
        self.assertIn('api@example.com', emails)
        self.assertTrue(all(e.endswith('@example.com') for e in emails))
        self.assertEqual(set(data['records'][0]), {'id', 'email'})
        echo = self.api('POST', '/custom/echo?q=1', {'a': 1}).json()
        self.assertEqual(echo, {'you_sent': {'a': 1}, 'user': 'api_user', 'q': '1'})
        self.api('POST', '/custom/touch', {'ids': [self.partner.id]})
        self.assertEqual(str(self.partner.comment), '<p>touched by the API</p>')
        self.assertEqual(self.api('GET', '/custom/nothing/here').status_code, 404)
        # public endpoints run as the public user, unless explicitly sudo
        public = Endpoint.create({'name': 'Public', 'path': 'public/jobs', 'mode': 'domain',
                                  'model_id': self.env['ir.model']._get('ir.cron').id, 'auth_required': False,
                                  'domain': "[('id', '=', %d)]" % self.env.ref('rest_api_gateway.ir_cron_rest_api_cleanup').id})
        self.assertEqual(self.api('GET', '/custom/public/jobs', key=False).status_code, 403)
        public.run_as = 'sudo'
        self.assertEqual(self.api('GET', '/custom/public/jobs', key=False).json()['count'], 1)
        with self.assertRaises(ValidationError):
            Endpoint.create({'name': 'Unsafe', 'path': 'unsafe', 'mode': 'code', 'auth_required': False,
                             'run_as': 'sudo', 'code': 'result = 1'})
        with self.assertRaises(ValidationError):
            Endpoint.create({'name': 'Bad path', 'path': 'a b', 'mode': 'code', 'code': 'result = 1'})

    # ------------------------------------------------------------------ operations
    def test_logs_rate_limit_and_masking(self):
        self.ICP.set_bool('rest_api_gateway.log_bodies', True)
        client = self.env['rest.api.client'].create({'name': 'Masked', 'user_id': self.user.id})
        secret = self.env['rest.api.secret.wizard'].browse(client.action_generate_secret()['res_id']).secret
        self.url_open('/api/v1/oauth2/token', data={'grant_type': 'client_credentials',
                                                    'client_id': client.client_id, 'client_secret': secret})
        log = self.env['rest.api.log'].search([('path', '=', '/api/v1/oauth2/token')], limit=1)
        self.assertIn('client_secret=***', log.request_body)
        self.assertNotIn(secret, log.request_body + log.response_body)
        self.ICP.set_int('rest_api_gateway.rate_limit', 3)
        statuses = [self.api('GET', '/me').status_code for _i in range(4)]
        self.assertEqual(statuses[-1], 429)
        self.assertIn('Retry-After', self.api('GET', '/me').headers)

    def test_download_and_report(self):
        self.partner.image_1920 = base64.b64encode(PNG).decode()
        response = self.api('GET', f'/res.partner/{self.partner.id}/image_1920/download')
        self.assertEqual(response.headers['Content-Type'], 'image/png')
        self.assertTrue(response.content.startswith(b'\x89PNG'))
        self.assertEqual(self.api('GET', f'/res.partner/{self.partner.id}/name/download').status_code, 400)
        base = self.env.ref('base.module_base')
        response = self.api('GET', f'/report/base.report_irmodulereference/{base.id}?format=html', key=self.admin_key)
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers['Content-Type'])
        self.assertEqual(self.api('GET', '/report/no.report/1', key=self.admin_key).status_code, 404)

    def test_openapi_docs_and_cors(self):
        self.env['rest.api.endpoint'].create({'name': 'Echo', 'path': 'echo/{word}', 'mode': 'code',
                                              'code': "result = params['word']"})
        self.assertEqual(self.url_open('/api/v1/openapi.json').status_code, 401)
        self.ICP.set_bool('rest_api_gateway.docs_public', True)
        spec = self.url_open('/api/v1/openapi.json').json()
        self.assertEqual(spec['openapi'], '3.0.3')
        self.assertEqual(spec['info']['title'], f'{self.env.company.name} REST API', 'anonymous request')
        self.assertIn('/res.partner/{id}', spec['paths'])
        self.assertIn('/custom/echo/{word}', spec['paths'])
        self.assertIn('email', spec['components']['schemas']['res_partner']['properties'])
        self.assertIn('api_docs.js', self.url_open('/api/docs').text)
        self.ICP.set_str('rest_api_gateway.cors_origins', 'https://app.example.com')
        preflight = self.url_open('/api/v1/res.partner', method='OPTIONS', headers={'Origin': 'https://app.example.com'})
        self.assertEqual(preflight.status_code, 204)
        self.assertEqual(preflight.headers['Access-Control-Allow-Origin'], 'https://app.example.com')
        other = self.api('GET', '/me', headers={'Origin': 'https://evil.example.com'})
        self.assertNotIn('Access-Control-Allow-Origin', other.headers)

    def test_docs_page_try_it(self):
        self.ICP.set_bool('rest_api_gateway.docs_public', True)
        code = """
            (async function () {
                const wait = async (sel) => {
                    for (let i = 0; i < 100; i++) {
                        const el = document.querySelector(sel);
                        if (el) { return el; }
                        await new Promise((r) => setTimeout(r, 100));
                    }
                    throw new Error('not found: ' + sel);
                };
                const op = [...(await wait('.op') && document.querySelectorAll('.op'))]
                    .find((o) => o.querySelector('.path').textContent === '/ping');
                op.open = true;
                op.querySelector('button.try').click();
                const status = await wait('.op[open] .status');
                if (status.textContent !== '200') { throw new Error('status ' + status.textContent); }
                console.log('test successful');
            })().catch((e) => console.error(e.message));
        """
        self.browser_js('/api/docs', code, ready='!!document.querySelector(".op")')

    def test_cleanup_cron(self):
        log = self.env['rest.api.log'].create({'method': 'GET', 'path': '/old', 'status': 200})
        self.env.cr.execute("UPDATE rest_api_log SET create_date = now() - interval '90 days' WHERE id = %s",
                            [log.id])
        self.env['rest.api.log']._cron_cleanup()
        self.assertFalse(log.exists())
