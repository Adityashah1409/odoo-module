from datetime import timedelta

import odoo
from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException


@tagged('post_install', '-at_install')
class TestLoginAs(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        for key, value in (('enabled', 'True'), ('require_reason', 'True'), ('notify_user', 'True'),
                           ('max_minutes', '60'), ('allow_portal', '')):
            cls.ICP.set_param('login_as_user.' + key, value)
        cls.admin = cls.env.ref('base.user_admin')
        cls.support = new_test_user(cls.env, 'support', groups='base.group_user,login_as_user.group_login_as',
                                    name='Sam Support')
        cls.sales = new_test_user(cls.env, 'salesrep', groups='base.group_user', name='Rita Sales')
        cls.other = new_test_user(cls.env, 'otto', groups='base.group_user', name='Otto Other')
        cls.boss = new_test_user(cls.env, 'boss', groups='base.group_system', name='Bea Boss')
        cls.portal = new_test_user(cls.env, 'paul', groups='base.group_portal', name='Paul Portal')
        cls.Log = cls.env['login.as.log']

    # helpers
    def _uid(self):
        return self.make_jsonrpc_request('/web/session/get_session_info')['uid']

    def _start(self, user, reason='Ticket 42'):
        return self.make_jsonrpc_request('/login_as/start', {'user_id': user.id, 'reason': reason})

    def _stop(self):
        return self.make_jsonrpc_request('/login_as/stop')

    def _logs(self, user):
        return self.Log.search([('origin_user_id', '=', user.id)], order='id')

    def _server_session(self):
        sid = self.opener.cookies.get('session_id')
        return odoo.http.root.session_store.get(sid)

    # tests
    def test_start_and_switch_back(self):
        self.authenticate('support', 'support')
        self.assertEqual(self._uid(), self.support.id)
        result = self._start(self.sales)
        self.assertEqual(result['url'], '/odoo')
        info = self.make_jsonrpc_request('/web/session/get_session_info')
        self.assertEqual(info['uid'], self.sales.id)
        self.assertEqual(info['login_as']['origin']['id'], self.support.id)
        self.assertGreater(info['login_as']['remaining'], 3500)
        log = self._logs(self.support)
        self.assertEqual(len(log), 1)
        self.assertRecordValues(log, [{'target_user_id': self.sales.id, 'state': 'active', 'reason': 'Ticket 42',
                                       'target_is_admin': False, 'target_share': False}])
        # the session really is Rita's: she cannot read the log model
        with self.assertRaises(JsonRpcException):
            self.make_jsonrpc_request('/web/dataset/call_kw/login.as.log/search_read', {
                'model': 'login.as.log', 'method': 'search_read', 'args': [], 'kwargs': {}})
        self.assertEqual(self._stop()['url'], '/odoo')
        self.assertEqual(self._uid(), self.support.id)
        log.invalidate_recordset()
        self.assertEqual(log.state, 'closed')
        self.assertEqual(log.end_reason, 'switch_back')
        self.assertTrue(log.end)
        # stop again is harmless
        self.assertEqual(self._stop()['url'], '/odoo')
        self.assertEqual(self._uid(), self.support.id)

    def test_target_is_notified(self):
        self.authenticate('support', 'support')
        self._start(self.sales, 'Checking the menus')
        message = self.env['mail.message'].search([('partner_ids', 'in', self.sales.partner_id.ids)],
                                                   order='id desc', limit=1)
        self.assertEqual(message.subject, 'Someone logged in as you')
        self.assertIn('Sam Support', message.body)
        self.assertIn('Checking the menus', message.body)
        self.assertEqual(message.author_id, self.support.partner_id)

    def test_reason_required(self):
        self.authenticate('support', 'support')
        with self.assertRaises(JsonRpcException):
            self._start(self.sales, reason='  ')
        self.assertEqual(self._uid(), self.support.id)
        self.assertFalse(self._logs(self.support))
        self.ICP.set_param('login_as_user.require_reason', '')
        self._start(self.sales, reason='')
        self.assertEqual(self._uid(), self.sales.id)

    def test_permissions(self):
        # no group
        self.authenticate('salesrep', 'salesrep')
        with self.assertRaises(JsonRpcException):
            self._start(self.other)
        self.assertEqual(self._uid(), self.sales.id)
        self.authenticate('support', 'support')
        for target in (self.support, self.boss, self.env['res.users'].browse(odoo.SUPERUSER_ID),
                       self.env.ref('base.public_user'), self.portal):
            with self.subTest(target=target.login):
                with self.assertRaises(JsonRpcException):
                    self._start(target)
                self.assertEqual(self._uid(), self.support.id)
        archived = new_test_user(self.env, 'gone', groups='base.group_user')
        archived.active = False
        with self.assertRaises(JsonRpcException):
            self._start(archived)
        # feature disabled
        self.ICP.set_param('login_as_user.enabled', '')
        with self.assertRaises(JsonRpcException):
            self._start(self.sales)
        self.assertFalse(self._logs(self.support))

    def test_admin_can_log_in_as_admin_and_portal(self):
        self.ICP.set_param('login_as_user.allow_portal', 'True')
        self.authenticate('admin', 'admin')
        self._start(self.boss)
        self.assertEqual(self._uid(), self.boss.id)
        self.assertTrue(self._logs(self.admin).target_is_admin)
        result = self._start(self.portal)
        self.assertIn(result['url'], ('/my', '/'))
        self.assertEqual(self._uid(), self.portal.id)
        self.assertEqual(self._stop()['url'], '/odoo')
        self.assertEqual(self._uid(), self.admin.id)

    def test_chained_switch_keeps_the_real_user(self):
        self.authenticate('support', 'support')
        self._start(self.sales)
        # Rita is not allowed to use the feature, but the real person behind the session is
        self._start(self.other, 'Second ticket')
        self.assertEqual(self._uid(), self.other.id)
        first, second = self._logs(self.support)
        self.assertEqual(first.end_reason, 'switch_other')
        self.assertEqual(second.origin_user_id, self.support)
        self.assertEqual(second.state, 'active')
        self._stop()
        self.assertEqual(self._uid(), self.support.id)
        second.invalidate_recordset()
        self.assertEqual(second.end_reason, 'switch_back')

    def test_time_limit(self):
        self.authenticate('support', 'support')
        self._start(self.sales)
        session = self._server_session()
        session['login_as_origin'] = dict(session['login_as_origin'], time=session['login_as_origin']['time'] - 3700)
        odoo.http.root.session_store.save(session)
        self.assertEqual(self._uid(), self.support.id)
        log = self._logs(self.support)
        self.assertEqual(log.end_reason, 'timeout')
        # no limit
        self.ICP.set_param('login_as_user.max_minutes', '0')
        self._start(self.sales)
        session = self._server_session()
        session['login_as_origin'] = dict(session['login_as_origin'], time=session['login_as_origin']['time'] - 99999)
        odoo.http.root.session_store.save(session)
        self.assertEqual(self._uid(), self.sales.id)

    def test_logout_closes_the_log(self):
        self.authenticate('support', 'support')
        self._start(self.sales)
        self.url_open('/web/session/logout', allow_redirects=False)
        log = self._logs(self.support)
        self.assertEqual(log.state, 'closed')
        self.assertEqual(log.end_reason, 'logout')

    def test_frontend_banner(self):
        self.authenticate('support', 'support')
        self._start(self.sales)
        response = self.url_open('/web/login')
        self.assertIn('o_login_as_frontend_banner', response.text)
        self.assertIn('Back to Sam Support', response.text)
        response = self.url_open('/login_as/back', allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self._uid(), self.support.id)

    def test_search_and_session_info(self):
        result = self.env['res.users'].with_user(self.support).login_as_search('')
        ids = {u['id'] for u in result['users']}
        self.assertIn(self.sales.id, ids)
        self.assertFalse(ids & {self.support.id, self.boss.id, self.portal.id, odoo.SUPERUSER_ID})
        self.assertTrue(result['require_reason'])
        self.assertEqual(result['max_minutes'], 60)
        result = self.env['res.users'].with_user(self.admin).login_as_search('Bea')
        self.assertEqual([u['name'] for u in result['users']], ['Bea Boss'])
        self.assertTrue(result['users'][0]['admin'])
        with self.assertRaises(odoo.exceptions.AccessError):
            self.env['res.users'].with_user(self.sales).login_as_search('')
        self.authenticate('salesrep', 'salesrep')
        info = self.make_jsonrpc_request('/web/session/get_session_info')
        self.assertFalse(info['login_as']['can'])
        self.authenticate('support', 'support')
        info = self.make_jsonrpc_request('/web/session/get_session_info')
        self.assertTrue(info['login_as']['can'])
        self.assertFalse(info['login_as']['origin'])

    def test_log_access_and_cron(self):
        self.authenticate('support', 'support')
        self._start(self.sales)
        self._stop()
        self.authenticate('admin', 'admin')
        self._start(self.other)
        self._stop()
        self.assertEqual(self.Log.with_user(self.support).search_count([]), 1)
        self.assertEqual(self.Log.with_user(self.admin).search_count([]), 2)
        self.assertEqual(self.sales.with_user(self.support).login_as_count, 1)
        old = self.Log.create({'origin_user_id': self.admin.id, 'target_user_id': self.sales.id,
                               'start': fields.Datetime.now() - timedelta(days=8)})
        recent = self.Log.create({'origin_user_id': self.admin.id, 'target_user_id': self.other.id,
                                  'start': fields.Datetime.now() - timedelta(minutes=150)})
        fresh = self.Log.create({'origin_user_id': self.admin.id, 'target_user_id': self.other.id})
        self.Log._cron_close_stale()
        self.assertEqual(old.end_reason, 'expired')
        self.assertEqual(recent.end_reason, 'timeout')
        self.assertEqual(fresh.state, 'active')

    def test_user_form_action(self):
        action = self.sales.with_user(self.support).action_login_as()
        self.assertEqual(action['tag'], 'login_as_user.switch')
        self.assertEqual(action['params']['user_id'], self.sales.id)
        action = self.sales.with_user(self.support).action_view_login_as_logs()
        self.assertEqual(action['res_model'], 'login.as.log')

    def test_tour(self):
        self.ICP.set_param('login_as_user.notify_user', '')
        self.start_tour('/odoo', 'login_as_user_tour', login='admin')
        log = self._logs(self.admin)
        self.assertEqual(log.target_user_id, self.sales)
        self.assertEqual(log.reason, 'Ticket 42: cannot find the contacts menu')
        self.assertEqual(log.end_reason, 'switch_back')
