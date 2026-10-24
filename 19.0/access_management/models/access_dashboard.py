from collections import Counter
from datetime import timedelta

from odoo import api, fields, models


class AccessDashboard(models.AbstractModel):
    _name = 'access.dashboard'
    _description = 'Access Management dashboard'

    @api.model
    def get_data(self):
        Rule = self.env['access.rule'].with_context(active_test=False)
        rules = Rule.search([])
        active = rules.filtered('active')
        effective = active.filtered('is_effective')
        now = fields.Datetime.now()
        week = now - timedelta(days=7)
        users = effective.effective_user_ids
        Log = self.env['access.export.log']
        Attempt = self.env['access.lock.attempt']

        model_counter = Counter()
        for rule in effective:
            for model in set(rule.model_line_ids.mapped('model_id.name') + rule.field_line_ids.mapped('model_id.name')
                             + rule.element_line_ids.mapped('model_id.name')):
                model_counter[model] += len(rule.effective_user_ids)
        user_counter = Counter()
        for rule in effective:
            for user in rule.effective_user_ids:
                user_counter[user.id] += 1
        top_users = self.env['res.users'].browse([uid for uid, _count in user_counter.most_common(6)])

        kinds = [
            ('menus', self.env._('Hidden menus'), len(effective.filtered('menu_ids'))),
            ('models', self.env._('Model rules'), len(effective.filtered('model_line_ids'))),
            ('fields', self.env._('Field rules'), len(effective.filtered('field_line_ids'))),
            ('elements', self.env._('Buttons and tabs'), len(effective.filtered('element_line_ids'))),
            ('readonly', self.env._('Read-only users'), len(effective.filtered('readonly_user'))),
            ('login', self.env._('Login / API / debug'),
             len(effective.filtered(lambda r: r.block_login or r.block_api or r.no_debug))),
        ]
        exports = Log.search([('create_date', '>=', week)])
        days = []
        for offset in range(6, -1, -1):
            day = fields.Date.context_today(self) - timedelta(days=offset)
            day_logs = exports.filtered(lambda l: fields.Datetime.context_timestamp(self, l.create_date).date() == day)
            days.append({'day': fields.Date.to_string(day), 'exports': len(day_logs),
                         'records': sum(day_logs.mapped('record_count'))})
        return {
            'kpis': {
                'rules': len(active),
                'effective': len(effective),
                'users': len(users),
                'menus': len(effective.menu_ids),
                'expired': len(active.filtered('is_expired')),
                'scheduled': len(active.filtered(lambda r: r.use_schedule or r.date_from or r.date_to)),
                'exports': len(exports),
                'alerts': len(exports.filtered('alert')),
                'locks': self.env['access.menu.lock'].search_count([]),
                'failed_pins': Attempt.search_count([('success', '=', False), ('create_date', '>=', week)]),
            },
            'kinds': [{'key': k, 'label': label, 'count': count} for k, label, count in kinds],
            'models': [{'name': name, 'count': count} for name, count in model_counter.most_common(6)],
            'users': [{'id': u.id, 'name': u.name, 'rules': user_counter[u.id]} for u in top_users],
            'days': days,
            'recent_exports': [{
                'id': log.id, 'user': log.user_id.name, 'model': log.model_name or log.model,
                'records': log.record_count, 'alert': log.alert,
                'date': fields.Datetime.to_string(log.create_date),
            } for log in Log.search([], limit=6)],
            'rules': [{
                'id': rule.id, 'name': rule.name, 'users': rule.user_count, 'effective': rule.is_effective,
                'expired': rule.is_expired, 'scheduled': bool(rule.use_schedule or rule.date_to),
                'summary': ', '.join(filter(None, [
                    rule.menu_count and self.env._('%s menus', rule.menu_count),
                    rule.model_count and self.env._('%s models', rule.model_count),
                    rule.field_count and self.env._('%s fields', rule.field_count),
                    rule.element_count and self.env._('%s buttons/tabs', rule.element_count),
                    rule.readonly_user and self.env._('read-only'),
                    rule.block_login and self.env._('no login'),
                    rule.block_api and self.env._('no API'),
                    rule.no_debug and self.env._('no debug'),
                ])),
            } for rule in active[:8]],
        }
