import time

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request

from odoo.addons.web.controllers.action import Action
from odoo.addons.web.controllers.dataset import DataSet
from odoo.addons.web.controllers.report import ReportController

SESSION_KEY = 'access_management_unlocked'


def _unlocked(lock_id):
    unlocked = request.session.get(SESSION_KEY) or {}
    return unlocked.get(str(lock_id), 0) > time.time()


class AccessAction(Action):

    @http.route()
    def load(self, action_id, context=None):
        result = super().load(action_id, context=context)
        if not result or not result.get('id') or not result.get('type', '').startswith('ir.actions.'):
            return result
        action = request.env[result['type']].sudo().browse(result['id'])
        if request.env['ir.ui.menu']._access_blocked_action(action):
            raise AccessError(request.env._('This menu is not available to you.'))
        lock = request.env['access.menu.lock']._lock_for_action(action)
        if lock and not _unlocked(lock.id):
            return {
                'type': 'ir.actions.client', 'tag': 'access_management.pin_prompt',
                'name': lock.menu_id.name, 'target': 'current',
                'params': {'lock_id': lock.id, 'action_id': result['id'], 'menu': lock.menu_id.complete_name,
                           'pin_type': lock.pin_type},
            }
        return result


class AccessDataSet(DataSet):

    @http.route()
    def call_button(self, model, method, args, kwargs, path=None):
        restrictions = request.env['access.rule']._get_restrictions()
        hidden = restrictions and restrictions['elements'].get(model, {}).get('button', ())
        if hidden and method in hidden:
            raise AccessError(request.env._('This button is not available to you.'))
        return super().call_button(model, method, args, kwargs, path=path)


class AccessReportController(ReportController):

    @http.route()
    def report_routes(self, reportname, docids=None, converter=None, **data):
        report = request.env['ir.actions.report'].sudo()._get_report_from_name(reportname)
        if report:
            info = request.env['access.rule']._model_restrictions(report.model)
            if info and (info.get('hide_all_reports') or report.id in info.get('report_ids', ())):
                raise AccessError(request.env._('This report is not available to you.'))
        return super().report_routes(reportname, docids=docids, converter=converter, **data)


class AccessManagement(http.Controller):

    @http.route('/access_management/unlock', type='jsonrpc', auth='user')
    def unlock(self, lock_id, code):
        lock = request.env['access.menu.lock'].sudo().browse(int(lock_id)).exists()
        if not lock or not lock._applies_to(request.env.user):
            return {'ok': False, 'message': request.env._('This lock does not exist anymore.')}
        ok, message = lock._try_unlock(request.env.user, code, ip=request.httprequest.remote_addr)
        if ok:
            unlocked = dict(request.session.get(SESSION_KEY) or {})
            unlocked[str(lock.id)] = time.time() + 60 * max(lock.unlock_minutes, 1)
            request.session[SESSION_KEY] = unlocked
        return {'ok': ok, 'message': message}
