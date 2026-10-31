import time

from markupsafe import Markup

from odoo import http
from odoo.addons.web.controllers.session import Session
from odoo.http import request


def _switch_session(user):
    """Point the current session at ``user``; the session id is rotated when the response is sent."""
    session = request.session
    env = request.env(user=user.id)
    session.update({
        'login': user.login,
        'uid': user.id,
        'context': dict(env['res.users'].context_get()),
        'session_token': user.with_user(user)._compute_session_token(session.sid),
    })
    session.should_rotate = True
    request.update_env(user=user.id)


def end_login_as(reason='switch_back'):
    """Close the running "login as" session and go back to the real user. Returns the url to open."""
    session = request.session
    origin_info = session.get('login_as_origin')
    if not origin_info:
        return '/odoo'
    # write first: on a read-only route this raises and the request is replayed in read/write mode
    request.env['login.as.log'].sudo().browse(origin_info['log_id'])._close(reason)
    origin = request.env['res.users'].sudo().browse(origin_info['uid'])
    session.pop('login_as_origin', None)
    if not origin.exists() or not origin.active:
        session.logout(keep_db=True)
        return '/web/login'
    _switch_session(origin)
    return '/odoo'


def _notify_target(origin, target, log):
    if not request.env['res.users']._login_as_param('notify_user') or not target.partner_id:
        return
    body = Markup('<p>%s</p>') % request.env._(
        '%(origin)s opened a session as you (%(login)s) on %(date)s. Reason: %(reason)s',
        origin=origin.name, login=target.login, date=log.start.strftime('%Y-%m-%d %H:%M UTC'),
        reason=log.reason or '-')
    request.env['mail.thread'].sudo().message_notify(
        partner_ids=target.partner_id.ids, author_id=origin.partner_id.id, body=body,
        subject=request.env._('Someone logged in as you'), email_layout_xmlid='mail.mail_notification_light')


class LoginAsController(http.Controller):

    @http.route('/login_as/start', type='jsonrpc', auth='user')
    def login_as_start(self, user_id, reason=''):
        Users = request.env['res.users'].sudo()
        session = request.session
        origin_info = session.get('login_as_origin')
        origin = Users.browse(origin_info['uid'] if origin_info else request.env.uid)
        target = Users.browse(int(user_id))
        Users._login_as_check(origin, target, reason)
        Log = request.env['login.as.log'].sudo()
        if origin_info:  # switching directly from one impersonated user to another
            Log.browse(origin_info['log_id'])._close('switch_other')
        log = Log.create({
            'origin_user_id': origin.id, 'target_user_id': target.id, 'reason': (reason or '').strip() or False,
            'ip_address': request.httprequest.remote_addr,
            'user_agent': (request.httprequest.user_agent.string or '')[:250],
            'target_is_admin': target.has_group('base.group_system'), 'target_share': target.share,
        })
        _notify_target(origin, target, log)
        # the web client of the target creates these on first load, which fails on read-only routes
        request.env['res.users.settings'].sudo()._find_or_create_for_user(target)
        session['login_as_origin'] = {'uid': origin.id, 'login': origin.login, 'name': origin.name,
                                      'log_id': log.id, 'time': time.time()}
        _switch_session(target)
        url = ('/my' if 'portal.mixin' in request.env else '/') if target.share else '/odoo'
        return {'url': url, 'log_id': log.id}

    @http.route('/login_as/stop', type='jsonrpc', auth='user')
    def login_as_stop(self):
        return {'url': end_login_as('switch_back')}

    @http.route('/login_as/back', type='http', auth='user', methods=['GET'])
    def login_as_back(self, **kw):
        """Link of the banner shown on the website / portal while logged in as someone else."""
        return request.redirect(end_login_as('switch_back'))


def _readonly_unless_login_as(controller, rule, args):
    return not request.session.get('login_as_origin')


class LoginAsSession(Session):

    @http.route(readonly=_readonly_unless_login_as)
    def logout(self, redirect='/odoo'):
        if request.session.get('login_as_origin'):
            info = request.session['login_as_origin']
            request.env['login.as.log'].sudo().browse(info['log_id'])._close('logout')
        return super().logout(redirect=redirect)
