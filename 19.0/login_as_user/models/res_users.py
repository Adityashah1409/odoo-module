from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.http import request

PARAM = 'login_as_user.'


class ResUsers(models.Model):
    _inherit = 'res.users'

    login_as_count = fields.Integer(compute='_compute_login_as_count', groups='login_as_user.group_login_as')

    def _compute_login_as_count(self):
        Log = self.env['login.as.log']
        for user in self:
            user.login_as_count = Log.search_count(
                ['|', ('origin_user_id', '=', user.id), ('target_user_id', '=', user.id)]) if user.id else 0

    @api.model
    def _login_as_param(self, key):
        return bool(self.env['ir.config_parameter'].sudo().get_param(PARAM + key))

    @api.model
    def _login_as_minutes(self):
        try:
            return max(int(self.env['ir.config_parameter'].sudo().get_param(PARAM + 'max_minutes') or 0), 0)
        except ValueError:
            return 0

    @api.model
    def _login_as_allowed_for(self, uid):
        """Can the user ``uid`` (the real person behind the session) log in as someone else?"""
        if not self._login_as_param('enabled'):
            return False
        user = self.sudo().browse(uid)
        return bool(user.exists()) and user.has_group('login_as_user.group_login_as')

    @api.model
    def _login_as_check(self, origin, target, reason=''):
        """Raise when ``origin`` may not open a session as ``target``."""
        env = self.env
        if not env['res.users']._login_as_allowed_for(origin.id):
            raise AccessError(env._('You are not allowed to log in as other users.'))
        if not target.exists() or not target.active:
            raise UserError(env._('This user does not exist or is archived.'))
        if target.id == 1 or target._is_superuser():
            raise AccessError(env._('Nobody can log in as the superuser.'))
        if target == origin:
            raise UserError(env._('Choose another user.'))
        if target._is_public():
            raise UserError(env._('The public user cannot be used.'))
        if target.share and not env['res.users']._login_as_param('allow_portal'):
            raise AccessError(env._('Logging in as portal users is disabled in the settings.'))
        if target.has_group('base.group_system') and not origin.has_group('base.group_system'):
            raise AccessError(env._('Only administrators can log in as an administrator.'))
        if env['res.users']._login_as_param('require_reason') and not (reason or '').strip():
            raise UserError(env._('Give a reason.'))
        if target.company_ids and not (target.company_ids & origin.company_ids) and not origin._is_system():
            raise AccessError(env._('This user works in companies you do not have access to.'))

    @api.model
    def login_as_search(self, term='', limit=20, user_id=False):
        """Users the current person may log in as, with their groups (for the switch screen)."""
        origin = self._login_as_origin()
        if not self._login_as_allowed_for(origin.id):
            raise AccessError(self.env._('You are not allowed to log in as other users.'))
        current = self.env.uid if origin != self.env.user else False
        domain = [('id', 'not in', [i for i in (1, origin.id, current) if i]), ('active', '=', True)]
        if not self._login_as_param('allow_portal'):
            domain.append(('share', '=', False))
        if term:
            domain += ['|', '|', ('name', 'ilike', term), ('login', 'ilike', term), ('email', 'ilike', term)]
        users = self.sudo().search(domain, limit=limit * 2, order='name')
        if user_id and not term:
            users = self.sudo().search(domain + [('id', '=', int(user_id))]) | users
        recent = self.env['login.as.log'].sudo().search([('origin_user_id', '=', origin.id)], limit=50)
        recent_ids = list(dict.fromkeys(recent.target_user_id.ids))[:5]
        result = []
        for user in users:
            if user._is_public() or (user.has_group('base.group_system') and not origin.has_group('base.group_system')):
                continue
            groups = user.all_group_ids.filtered(lambda g: g.privilege_id or g == self.env.ref('base.group_system'))
            result.append({
                'id': user.id, 'name': user.name, 'login': user.login, 'portal': user.share,
                'admin': user.has_group('base.group_system'), 'company': user.company_id.name,
                'groups': sorted({f'{g.privilege_id.name} / {g.name}' if g.privilege_id else g.name for g in groups}),
                'recent': user.id in recent_ids,
                'login_date': fields.Datetime.to_string(user.login_date) if user.login_date else False,
            })
            if len(result) >= limit:
                break
        return {
            'users': result,
            'require_reason': self._login_as_param('require_reason'),
            'max_minutes': self._login_as_minutes(),
            'origin': origin.name,
        }

    @api.model
    def _login_as_origin(self):
        origin = request and request.session.get('login_as_origin')
        return self.sudo().browse(origin['uid']) if origin else self.env.user

    def action_login_as(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'login_as_user.switch', 'name': self.env._('Log in as'),
                'params': {'user_id': self.id}}

    def action_view_login_as_logs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('login_as_user.action_login_as_log')
        action['domain'] = ['|', ('origin_user_id', '=', self.id), ('target_user_id', '=', self.id)]
        return action
