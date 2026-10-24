from odoo import api, fields, models
from odoo.exceptions import AccessDenied


class ResUsers(models.Model):
    _inherit = 'res.users'

    access_rule_ids = fields.Many2many('access.rule', compute='_compute_access_rule_ids', string='Access rules')
    access_rule_count = fields.Integer(compute='_compute_access_rule_ids')

    def _compute_access_rule_ids(self):
        rules = self.env['access.rule'].sudo().search([])
        for user in self:
            applicable = rules.filtered(lambda r: user in r.effective_user_ids)
            user.access_rule_ids = applicable
            user.access_rule_count = len(applicable)

    def _check_credentials(self, credential, env):
        auth_info = super()._check_credentials(credential, env)
        self._am_check_login(interactive=(env or {}).get('interactive', True))
        return auth_info

    def _am_check_login(self, interactive=True):
        Rule = self.env['access.rule'].sudo()
        restrictions = Rule._restrictions_for(self.env.user.id, self.env.user.company_id.id)
        if restrictions and (restrictions['block_login'] or (not interactive and restrictions['block_api'])):
            raise AccessDenied(self.env._('Your access is restricted at the moment.'))

    def action_view_access_rules(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'access.rule', 'name': self.env._('Access rules'),
            'views': [(False, 'list'), (False, 'form')], 'domain': [('id', 'in', self.access_rule_ids.ids)],
        }


class ResUsersApikeys(models.Model):
    _inherit = 'res.users.apikeys'

    @api.model
    def _check_credentials(self, *, scope, key):
        uid = super()._check_credentials(scope=scope, key=key)
        if uid:
            user = self.env['res.users'].sudo().browse(uid)
            restrictions = self.env['access.rule'].sudo()._restrictions_for(uid, user.company_id.id)
            if restrictions and (restrictions['block_api'] or restrictions['block_login']):
                return None
        return uid
