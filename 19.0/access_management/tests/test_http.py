import odoo
from odoo.tests import HttpCase, JsonRpcException, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHttp(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.team = cls.env['res.groups'].create({'name': 'AM http team'})
        groups = 'base.group_user,base.group_partner_manager,base.group_allow_export'
        cls.alice = new_test_user(cls.env, 'am_http_alice', groups=groups, name='Alice Http')
        cls.alice.group_ids |= cls.team
        cls.bob = new_test_user(cls.env, 'am_http_bob', groups=groups, name='Bob Http')
        cls.partner = cls.env['res.partner'].create({'name': 'Harbour Supplies', 'city': 'Bristol'})
        cls.partner_model = cls.env['ir.model']._get('res.partner')
        cls.partner_action = cls.env['ir.actions.act_window'].create({
            'name': 'AM partners', 'res_model': 'res.partner', 'view_mode': 'list,form'})
        cls.partner_menu = cls.env['ir.ui.menu'].create({
            'name': 'AM partners', 'parent_id': cls.env.ref('mail.menu_root_discuss').id,
            'action': f'ir.actions.act_window,{cls.partner_action.id}'})

    def rule(self, **vals):
        vals.setdefault('name', 'Http rule')
        vals.setdefault('user_ids', [(6, 0, self.alice.ids)])
        return self.env['access.rule'].create(vals)

    def call_kw(self, model, method, args, kwargs=None):
        return self.make_jsonrpc_request(f'/web/dataset/call_kw/{model}/{method}', {
            'model': model, 'method': method, 'args': args, 'kwargs': kwargs or {}})

    def test_pin_protected_menu(self):
        lock = self.env['access.menu.lock'].create({'menu_id': self.partner_menu.id, 'code': '2468',
                                                    'user_ids': [(6, 0, self.alice.ids)]})
        self.authenticate('am_http_alice', 'am_http_alice')
        result = self.make_jsonrpc_request('/web/action/load', {'action_id': self.partner_action.id})
        self.assertEqual(result['tag'], 'access_management.pin_prompt')
        self.assertEqual(result['params']['lock_id'], lock.id)
        answer = self.make_jsonrpc_request('/access_management/unlock', {'lock_id': lock.id, 'code': '1111'})
        self.assertFalse(answer['ok'])
        answer = self.make_jsonrpc_request('/access_management/unlock', {'lock_id': lock.id, 'code': '2468'})
        self.assertTrue(answer['ok'])
        result = self.make_jsonrpc_request('/web/action/load', {'action_id': self.partner_action.id})
        self.assertEqual(result['res_model'], 'res.partner')
        self.assertEqual(lock.attempt_ids.mapped('success'), [True, False])
        # not concerned users open the menu directly
        self.authenticate('am_http_bob', 'am_http_bob')
        result = self.make_jsonrpc_request('/web/action/load', {'action_id': self.partner_action.id})
        self.assertEqual(result['res_model'], 'res.partner')

    def test_hidden_menu_action(self):
        self.rule(menu_ids=[(6, 0, self.partner_menu.ids)])
        self.authenticate('am_http_alice', 'am_http_alice')
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request('/web/action/load', {'action_id': self.partner_action.id})
        self.authenticate('am_http_bob', 'am_http_bob')
        self.assertTrue(self.make_jsonrpc_request('/web/action/load', {'action_id': self.partner_action.id}))

    def test_buttons_duplicate_and_fields_over_rpc(self):
        self.rule(
            element_line_ids=[(0, 0, {'model_id': self.partner_model.id, 'element_type': 'button',
                                      'name': 'action_archive'})],
            model_line_ids=[(0, 0, {'model_id': self.partner_model.id, 'no_duplicate': True})],
            field_line_ids=[(0, 0, {'model_id': self.partner_model.id, 'mode': 'readonly',
                                    'field_id': self.env['ir.model.fields']._get('res.partner', 'city').id})],
        )
        self.authenticate('am_http_alice', 'am_http_alice')
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request('/web/dataset/call_button/res.partner/action_archive', {
                'model': 'res.partner', 'method': 'action_archive', 'args': [[self.partner.id]], 'kwargs': {}})
        with self.assertRaises(JsonRpcException):
            self.call_kw('res.partner', 'copy', [[self.partner.id]])
        with self.assertRaises(JsonRpcException):
            self.call_kw('res.partner', 'write', [[self.partner.id], {'city': 'Leeds'}])
        self.call_kw('res.partner', 'write', [[self.partner.id], {'name': 'Harbour Supplies Ltd'}])
        self.assertTrue(self.partner.active)
        self.authenticate('am_http_bob', 'am_http_bob')
        self.call_kw('res.partner', 'copy', [[self.partner.id]])
        self.call_kw('res.partner', 'write', [[self.partner.id], {'city': 'Leeds'}])
        self.assertEqual(self.partner.city, 'Leeds')

    def test_chatter_post(self):
        self.rule(model_line_ids=[(0, 0, {'model_id': self.partner_model.id, 'hide_send_message': True})])
        self.authenticate('am_http_alice', 'am_http_alice')

        def post(subtype):
            return self.make_jsonrpc_request('/mail/message/post', {
                'thread_model': 'res.partner', 'thread_id': self.partner.id,
                'post_data': {'body': 'Hello', 'message_type': 'comment', 'subtype_xmlid': subtype}})

        with self.assertRaises(JsonRpcException):
            post('mail.mt_comment')
        post('mail.mt_note')   # log notes are still allowed
        self.assertIn('Hello', self.partner.message_ids[0].body)

    def test_debug_mode(self):
        self.rule(no_debug=True)
        self.authenticate('am_http_alice', 'am_http_alice')
        self.url_open('/odoo?debug=1')
        self.assertEqual(odoo.http.root.session_store.get(self.session.sid).debug, '')
        self.authenticate('am_http_bob', 'am_http_bob')
        self.url_open('/odoo?debug=1')
        self.assertEqual(odoo.http.root.session_store.get(self.session.sid).debug, '1')

    def test_report_route(self):
        self.env['ir.ui.view'].create({
            'name': 'am_test_partner_report', 'type': 'qweb', 'key': 'access_management.am_test_partner_report',
            'arch': '<t t-name="access_management.am_test_partner_report"><t t-foreach="docs" t-as="o">'
                    '<p t-out="o.name"/></t></t>'})
        report = self.env['ir.actions.report'].create({
            'name': 'AM partner sheet', 'model': 'res.partner', 'report_type': 'qweb-html',
            'report_name': 'access_management.am_test_partner_report'})
        url = f'/report/html/access_management.am_test_partner_report/{self.partner.id}'
        self.authenticate('am_http_alice', 'am_http_alice')
        self.assertIn('Harbour Supplies', self.url_open(url).text)
        self.rule(model_line_ids=[(0, 0, {'model_id': self.partner_model.id, 'report_ids': [(6, 0, report.ids)]})])
        response = self.url_open(url)
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn('Harbour Supplies', response.text)

    def test_tour_dashboard(self):
        self.rule(name='Tour rule: no delete',
                  model_line_ids=[(0, 0, {'model_id': self.partner_model.id, 'no_delete': True})])
        self.start_tour('/odoo/access-dashboard', 'access_management_dashboard_tour', login='admin')

    def test_tour_pin(self):
        self.env['access.menu.lock'].create({'menu_id': self.partner_menu.id, 'code': '2468'})
        # the list also loses "Export" in its action menu (checked at the end of the tour)
        self.rule(model_line_ids=[(0, 0, {'model_id': self.partner_model.id, 'no_export': True})])
        self.start_tour(f'/odoo/action-{self.partner_action.id}', 'access_management_pin_tour', login='am_http_alice')
