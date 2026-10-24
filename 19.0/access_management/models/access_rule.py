import logging
from datetime import datetime

import pytz

from odoo import api, fields, models, tools
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools.safe_eval import safe_eval, time

from odoo.addons.base.models.res_partner import _tz_get

_logger = logging.getLogger(__name__)

WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
# models that a rule never restricts: this module (no lock-out) and the plumbing every user needs
EXEMPT_MODELS = ('access.',)
READONLY_USER_EXEMPT = ('ir.', 'bus.', 'mail.', 'discuss.', 'res.users', 'res.device', 'web_tour.', 'access.',
                        'base.', 'base_import.', 'iap.', 'auth_totp.', 'portal.', 'digest.')
CHATTER_FLAGS = ('hide_chatter', 'hide_send_message', 'hide_log_note', 'hide_activities', 'hide_followers',
                 'hide_attachments')
MODEL_FLAGS = ('no_create', 'no_edit', 'no_delete', 'no_duplicate', 'no_archive', 'no_import', 'no_export',
               'hide_all_reports', 'hide_all_actions', 'hide_search_panel', 'hide_filters', 'hide_group_by')
FIELD_MODES = {'invisible': 40, 'mask': 30, 'readonly': 20, 'required': 10}


class AccessRule(models.Model):
    _name = 'access.rule'
    _description = 'Access Rule'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, tracking=True)
    description = fields.Text()
    color = fields.Integer()

    # who
    user_ids = fields.Many2many('res.users', 'access_rule_user_rel', 'rule_id', 'user_id', string='Users',
                                domain="[('share', '=', False)]")
    group_ids = fields.Many2many('res.groups', 'access_rule_group_rel', 'rule_id', 'group_id', string='Groups',
                                 help='Members of these groups, including groups that imply them.')
    exclude_user_ids = fields.Many2many('res.users', 'access_rule_exclude_user_rel', 'rule_id', 'user_id',
                                        string='Except', domain="[('share', '=', False)]")
    company_ids = fields.Many2many('res.company', string='Companies',
                                   help='Apply only while the user works in one of these companies. Empty: all.')
    effective_user_ids = fields.Many2many('res.users', compute='_compute_effective_user_ids', string='Applies to')
    user_count = fields.Integer(compute='_compute_effective_user_ids', string='Users concerned')

    # when
    date_from = fields.Datetime('Valid from')
    date_to = fields.Datetime('Valid until', help='The rule stops applying after this date (expired).')
    use_schedule = fields.Boolean('Only during a weekly window')
    mon = fields.Boolean('Mon', default=True)
    tue = fields.Boolean('Tue', default=True)
    wed = fields.Boolean('Wed', default=True)
    thu = fields.Boolean('Thu', default=True)
    fri = fields.Boolean('Fri', default=True)
    sat = fields.Boolean('Sat', default=True)
    sun = fields.Boolean('Sun', default=True)
    hour_from = fields.Float('From', default=0.0)
    hour_to = fields.Float('To', default=24.0)
    tz = fields.Selection(_tz_get, string='Timezone', default=lambda self: self.env.user.tz or 'UTC')
    is_effective = fields.Boolean('Applying now', readonly=True, copy=False,
                                  help='Active, within its dates and its weekly window. Refreshed every 5 minutes.')
    is_expired = fields.Boolean(compute='_compute_is_expired', search='_search_is_expired')

    # what: global
    readonly_user = fields.Boolean('Read-only user', tracking=True,
                                   help='Users cannot create, edit or delete business records (chat and their '
                                        'preferences still work).')
    no_debug = fields.Boolean('Disable developer mode', tracking=True)
    block_api = fields.Boolean('Block external API', tracking=True,
                               help='XML-RPC / JSON-RPC logins and API keys are refused.')
    block_login = fields.Boolean('Block login', tracking=True,
                                 help='New logins are refused while the rule applies (combine with a weekly '
                                      'window to allow logins only during working hours).')

    # what: menus, models, fields, elements
    menu_ids = fields.Many2many('ir.ui.menu', 'access_rule_menu_rel', 'rule_id', 'menu_id', string='Hidden menus')
    block_menu_actions = fields.Boolean('Block their actions', default=True,
                                        help='Opening the action of a hidden menu by URL is refused too, unless a '
                                             'visible menu opens the same action.')
    model_line_ids = fields.One2many('access.rule.model', 'rule_id', string='Models', copy=True)
    field_line_ids = fields.One2many('access.rule.field', 'rule_id', string='Fields', copy=True)
    element_line_ids = fields.One2many('access.rule.element', 'rule_id', string='Buttons and tabs', copy=True)

    menu_count = fields.Integer(compute='_compute_counts')
    model_count = fields.Integer(compute='_compute_counts')
    field_count = fields.Integer(compute='_compute_counts')
    element_count = fields.Integer(compute='_compute_counts')

    _check_hours = models.Constraint(
        'CHECK (hour_from >= 0 AND hour_to <= 24 AND hour_from < hour_to)',
        'The window must start before it ends, between 00:00 and 24:00.',
    )

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rule in self:
            if rule.date_from and rule.date_to and rule.date_from > rule.date_to:
                raise ValidationError(self.env._('"Valid until" must be after "Valid from".'))

    # ------------------------------------------------------------------ computes
    @api.depends('user_ids', 'group_ids', 'exclude_user_ids')
    def _compute_effective_user_ids(self):
        for rule in self:
            users = rule.user_ids | rule.group_ids.all_user_ids
            users = users.filtered(lambda u: not u.share and u.id != 1) - rule.exclude_user_ids
            rule.effective_user_ids = users
            rule.user_count = len(users)

    @api.depends('menu_ids', 'model_line_ids', 'field_line_ids', 'element_line_ids')
    def _compute_counts(self):
        for rule in self:
            rule.menu_count = len(rule.menu_ids)
            rule.model_count = len(rule.model_line_ids)
            rule.field_count = len(rule.field_line_ids)
            rule.element_count = len(rule.element_line_ids)

    @api.depends('date_to')
    def _compute_is_expired(self):
        now = fields.Datetime.now()
        for rule in self:
            rule.is_expired = bool(rule.date_to and rule.date_to < now)

    def _search_is_expired(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            return NotImplemented
        expired = (operator == '=') == value
        now = fields.Datetime.now()
        return [('date_to', '<', now)] if expired else ['|', ('date_to', '=', False), ('date_to', '>=', now)]

    def _effective_at(self, when):
        """Is the rule applying at ``when`` (naive UTC)?"""
        self.ensure_one()
        if not self.active or (self.date_from and when < self.date_from) or (self.date_to and when > self.date_to):
            return False
        if not self.use_schedule:
            return True
        local = pytz.utc.localize(when).astimezone(pytz.timezone(self.tz or 'UTC'))
        if not self[WEEKDAYS[local.weekday()]]:
            return False
        hour = local.hour + local.minute / 60.0
        return self.hour_from <= hour < self.hour_to

    # ------------------------------------------------------------------ CRUD and cache
    @api.model_create_multi
    def create(self, vals_list):
        rules = super().create(vals_list)
        rules._refresh_effective(force_clear=True)
        return rules

    def write(self, vals):
        res = super().write(vals)
        if set(vals) - {'is_effective', 'description', 'color', 'sequence'}:
            self._refresh_effective(force_clear=True)
        return res

    def unlink(self):
        res = super().unlink()
        self.env.registry.clear_cache()
        return res

    def _refresh_effective(self, force_clear=False):
        """Store whether each rule applies now; clear the caches when something changed."""
        now = fields.Datetime.now()
        changed = False
        for rule in self.with_context(active_test=False):
            effective = rule._effective_at(now)
            if rule.is_effective != effective:
                super(AccessRule, rule).write({'is_effective': effective})
                changed = True
        if changed or force_clear:
            self.env.registry.clear_cache()
        return changed

    @api.model
    def _cron_refresh(self):
        rules = self.with_context(active_test=False).search([])
        if rules._refresh_effective():
            _logger.info('Access rules: effective state changed, caches cleared')

    def action_refresh_cache(self):
        self.with_context(active_test=False).search([])._refresh_effective(force_clear=True)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': self.env._('Access caches refreshed. Users see the change after a reload.'),
            'next': {'type': 'ir.actions.client', 'tag': 'reload'}}}

    @api.model
    def action_archive_expired(self):
        expired = self.search([('is_expired', '=', True)])
        expired.action_archive()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'info', 'message': self.env._('%s expired rule(s) archived.', len(expired)),
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    def action_view_users(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'res.users', 'name': self.env._('Users concerned'),
            'views': [(False, 'list'), (False, 'form')], 'domain': [('id', 'in', self.effective_user_ids.ids)],
        }

    # ------------------------------------------------------------------ restrictions of the current user
    @api.model
    def _get_restrictions(self):
        """Restrictions of the current user in the current company, ``None`` when there are none."""
        env = self.env
        if env.su or env.uid == 1 or not env.uid:
            return None
        return self._restrictions_for(env.uid, env.company.id)

    @api.model
    @tools.ormcache('uid', 'company_id')
    def _restrictions_for(self, uid, company_id):
        Rule = self.sudo().with_context(active_test=True)
        user = self.env['res.users'].sudo().browse(uid)
        if not user.exists() or user.share:
            return None
        groups = user.all_group_ids
        rules = Rule.search([('is_effective', '=', True)]).filtered(
            lambda r: (user in r.user_ids or (r.group_ids & groups))
            and user not in r.exclude_user_ids
            and (not r.company_ids or company_id in r.company_ids.ids)
        )
        if not rules:
            return None
        menus = rules.menu_ids
        Menu = self.env['ir.ui.menu'].sudo().with_context(active_test=False)
        hidden_menus = Menu.search([('id', 'child_of', menus.ids)]) if menus else Menu
        if hidden_menus and user.has_group('access_management.group_access_manager'):
            # never lock an access manager out of this application
            own = self.env.ref('access_management.menu_access_root', raise_if_not_found=False)
            if own:
                hidden_menus -= Menu.search([('id', 'child_of', own.id)])
                hidden_menus -= own.parent_id
        result = {
            'rule_ids': tuple(rules.ids),
            'menus': frozenset(hidden_menus.ids),
            'block_menu_actions': any(rules.filtered('menu_ids').mapped('block_menu_actions')),
            'readonly_user': any(rules.mapped('readonly_user')),
            'no_debug': any(rules.mapped('no_debug')),
            'block_api': any(rules.mapped('block_api')),
            'block_login': any(rules.mapped('block_login')),
            'models': {},
            'fields': {},
            'elements': {},
        }
        for line in rules.model_line_ids:
            model = line.model_id.model
            if not model or model.startswith(EXEMPT_MODELS):
                continue
            info = result['models'].setdefault(model, {
                'ops': set(), 'domains': [], 'report_ids': set(), 'action_ids': set(),
                **dict.fromkeys(MODEL_FLAGS + CHATTER_FLAGS, False)})
            for flag in MODEL_FLAGS + CHATTER_FLAGS:
                info[flag] = info[flag] or line[flag]
            if line.readonly or line.no_create:
                info['ops'].add('create')
            if line.readonly or line.no_edit:
                info['ops'].add('write')
            if line.readonly or line.no_delete:
                info['ops'].add('unlink')
            if line.readonly:
                info.update(no_duplicate=True, no_archive=True, no_import=True)
            if line.domain and line.domain.strip() not in ('', '[]'):
                info['domains'].append(line.domain)
            info['report_ids'].update(line.report_ids.ids)
            info['action_ids'].update(line.action_ids.ids + line.window_action_ids.ids)
        for line in rules.field_line_ids:
            model, fname = line.model_id.model, line.field_id.name
            if not model or not fname or model.startswith(EXEMPT_MODELS):
                continue
            current = result['fields'].setdefault(model, {}).get(fname)
            if current and FIELD_MODES[current['mode']] >= FIELD_MODES[line.mode]:
                continue
            result['fields'][model][fname] = {
                'mode': line.mode, 'start': line.mask_start, 'end': line.mask_end,
                'domain': line.domain if line.domain and line.domain.strip() not in ('', '[]') else None,
            }
        for line in rules.element_line_ids:
            model = line.model_id.model
            if not model or model.startswith(EXEMPT_MODELS):
                continue
            elements = result['elements'].setdefault(model, {'button': set(), 'page': set()})
            elements[line.element_type].add(line.name.strip())
        return result

    @api.model
    def _model_restrictions(self, model_name):
        restrictions = self._get_restrictions()
        return restrictions and restrictions['models'].get(model_name)

    @api.model
    def _eval_context(self):
        return {
            'user': self.env.user.with_context({}),
            'time': time,
            'datetime': datetime,
            'company_id': self.env.company.id,
            'company_ids': self.env.companies.ids,
            'context_today': lambda: fields.Date.context_today(self),
        }

    @api.model
    def _restriction_domain(self, model_name, operation):
        """Extra security domain for ``model_name`` / ``operation``, or ``None``."""
        restrictions = self._get_restrictions()
        if not restrictions:
            return None
        info = restrictions['models'].get(model_name)
        blocked = info and operation in info['ops']
        if (operation != 'read' and restrictions['readonly_user'] and not model_name.startswith(READONLY_USER_EXEMPT)
                and not self.env[model_name]._transient):
            blocked = True
        if blocked:
            return Domain.FALSE
        if info and info['domains']:
            context = self._eval_context()
            return Domain.AND([Domain(safe_eval(domain, context)) for domain in info['domains']])
        return None
