import base64
import json

from odoo import api, fields, models
from odoo.exceptions import UserError

FORMAT_VERSION = 1
RULE_FLAGS = ('active', 'sequence', 'description', 'date_from', 'date_to', 'use_schedule', 'mon', 'tue', 'wed',
              'thu', 'fri', 'sat', 'sun', 'hour_from', 'hour_to', 'tz', 'readonly_user', 'no_debug', 'block_api',
              'block_login', 'block_menu_actions')
MODEL_FLAGS = ('readonly', 'no_create', 'no_edit', 'no_delete', 'no_duplicate', 'no_archive', 'no_import',
               'no_export', 'domain', 'hide_chatter', 'hide_send_message', 'hide_log_note', 'hide_activities',
               'hide_followers', 'hide_attachments', 'hide_all_reports', 'hide_all_actions', 'hide_search_panel',
               'hide_filters', 'hide_group_by')


class _DryRun(Exception):
    pass


class AccessRuleTransfer(models.TransientModel):
    _name = 'access.rule.transfer'
    _description = 'Export / import access rules'

    mode = fields.Selection([('export', 'Export'), ('import', 'Import')], default='export', required=True)
    rule_ids = fields.Many2many('access.rule', string='Rules', help='Empty: all rules.',
                                default=lambda self: self.env.context.get('active_ids')
                                if self.env.context.get('active_model') == 'access.rule' else False)
    file = fields.Binary('JSON file', attachment=False)
    file_name = fields.Char()
    dry_run = fields.Boolean('Dry run', default=True, help='Check the file and show what would change, without saving.')
    result = fields.Text(readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], default='draft')

    # ------------------------------------------------------------------ references
    @api.model
    def _xmlid(self, record):
        data = self.env['ir.model.data'].sudo().search_fetch(
            [('model', '=', record._name), ('res_id', '=', record.id)], ['module', 'name'], limit=1)
        return f'{data.module}.{data.name}' if data else None

    @api.model
    def _ref(self, record, key_field):
        return {'xmlid': self._xmlid(record), 'name': record[key_field]}

    @api.model
    def _find(self, model, ref, key_field, extra_domain=()):
        if not ref:
            return self.env[model]
        if isinstance(ref, str):
            ref = {'name': ref}
        if ref.get('xmlid'):
            record = self.env.ref(ref['xmlid'], raise_if_not_found=False)
            if record and record._name == model:
                return record
        if ref.get('name'):
            return self.env[model].sudo().with_context(active_test=False).search(
                [(key_field, '=', ref['name']), *extra_domain], limit=1)
        return self.env[model]

    # ------------------------------------------------------------------ export
    @api.model
    def _serialize(self, rules):
        out = []
        for rule in rules:
            out.append({
                'name': rule.name,
                **{flag: (fields.Datetime.to_string(rule[flag]) if rule._fields[flag].type == 'datetime' else rule[flag])
                   for flag in RULE_FLAGS},
                'users': [u.login for u in rule.user_ids],
                'exclude_users': [u.login for u in rule.exclude_user_ids],
                'groups': [self._ref(g, 'name') for g in rule.group_ids],
                'companies': rule.company_ids.mapped('name'),
                'menus': [self._ref(m, 'complete_name') for m in rule.menu_ids],
                'models': [{
                    'model': line.model_id.model, **{flag: line[flag] for flag in MODEL_FLAGS},
                    'reports': [self._ref(r, 'report_name') for r in line.report_ids],
                    'actions': [self._ref(a, 'name') for a in line.action_ids],
                    'wizards': [self._ref(a, 'name') for a in line.window_action_ids],
                } for line in rule.model_line_ids],
                'fields': [{
                    'model': line.model_id.model, 'field': line.field_id.name, 'mode': line.mode,
                    'mask_start': line.mask_start, 'mask_end': line.mask_end, 'domain': line.domain,
                } for line in rule.field_line_ids],
                'elements': [{
                    'model': line.model_id.model, 'type': line.element_type, 'name': line.name,
                } for line in rule.element_line_ids],
            })
        return {'format': 'access_management', 'version': FORMAT_VERSION, 'rules': out}

    def action_export(self):
        self.ensure_one()
        rules = self.rule_ids or self.env['access.rule'].with_context(active_test=False).search([])
        payload = json.dumps(self._serialize(rules), indent=2, ensure_ascii=False, default=str)
        self.write({'file': base64.b64encode(payload.encode()).decode(), 'file_name': 'access_rules.json', 'state': 'done',
                    'result': self.env._('%s rule(s) exported.', len(rules))})
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': f'/web/content/access.rule.transfer/{self.id}/file/access_rules.json?download=true'}

    # ------------------------------------------------------------------ import
    def action_import(self):
        self.ensure_one()
        if not self.file:
            raise UserError(self.env._('Choose a JSON file exported by Access Management.'))
        try:
            data = json.loads(bytes(self.file))
        except ValueError as exc:
            raise UserError(self.env._('This is not a valid JSON file: %s', exc)) from exc
        if not isinstance(data, dict) or data.get('format') != 'access_management':
            raise UserError(self.env._('This file was not exported by Access Management.'))
        report = {'created': [], 'updated': [], 'skipped': [], 'failed': [], 'warnings': []}
        try:
            with self.env.cr.savepoint():
                for item in data.get('rules', []):
                    self._import_rule(item, report)
                if self.dry_run:
                    raise _DryRun()
        except _DryRun:
            self.env.invalidate_all()
        lines = [self.env._('Dry run: nothing was saved.') if self.dry_run else self.env._('Import done.')]
        for key, label in (('created', self.env._('Created')), ('updated', self.env._('Updated')),
                           ('skipped', self.env._('Skipped')), ('failed', self.env._('Failed')),
                           ('warnings', self.env._('Warnings'))):
            lines.append(f'{label}: {len(report[key])}')
            lines.extend(f'  - {entry}' for entry in report[key])
        self.write({'result': '\n'.join(lines), 'state': 'done'})
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
                'views': [(False, 'form')], 'target': 'new', 'name': self.env._('Import access rules')}

    def _import_rule(self, item, report):
        name = (item.get('name') or '').strip()
        if not name:
            report['failed'].append(self.env._('A rule without a name'))
            return
        warnings = []

        def many(model, refs, key_field):
            records = self.env[model]
            for ref in refs or []:
                record = self._find(model, ref, key_field)
                if record:
                    records |= record
                else:
                    warnings.append(self.env._('%(rule)s: %(model)s "%(ref)s" not found', rule=name, model=model,
                                               ref=ref.get('name') if isinstance(ref, dict) else ref))
            return records

        vals = {flag: item[flag] for flag in RULE_FLAGS if flag in item}
        vals.update({
            'name': name,
            'user_ids': [(6, 0, many('res.users', [{'name': login} for login in item.get('users', [])], 'login').ids)],
            'exclude_user_ids': [(6, 0, many('res.users', [{'name': login} for login in item.get('exclude_users', [])],
                                             'login').ids)],
            'group_ids': [(6, 0, many('res.groups', item.get('groups'), 'name').ids)],
            'company_ids': [(6, 0, many('res.company', item.get('companies'), 'name').ids)],
            'menu_ids': [(6, 0, many('ir.ui.menu', item.get('menus'), 'complete_name').ids)],
        })
        IrModel = self.env['ir.model'].sudo()
        model_lines, field_lines, element_lines = [(5, 0, 0)], [(5, 0, 0)], [(5, 0, 0)]
        for line in item.get('models', []):
            model = IrModel._get(line.get('model'))
            if not model:
                warnings.append(self.env._('%(rule)s: model %(model)s not installed', rule=name, model=line.get('model')))
                continue
            line_vals = {flag: line[flag] for flag in MODEL_FLAGS if flag in line}
            line_vals.update(model_id=model.id,
                             report_ids=[(6, 0, many('ir.actions.report', line.get('reports'), 'report_name').ids)],
                             action_ids=[(6, 0, many('ir.actions.server', line.get('actions'), 'name').ids)],
                             window_action_ids=[(6, 0, many('ir.actions.act_window', line.get('wizards'), 'name').ids)])
            model_lines.append((0, 0, line_vals))
        for line in item.get('fields', []):
            model = IrModel._get(line.get('model'))
            field = model and self.env['ir.model.fields'].sudo()._get(model.model, line.get('field'))
            if not field:
                warnings.append(self.env._('%(rule)s: field %(model)s.%(field)s not found', rule=name,
                                           model=line.get('model'), field=line.get('field')))
                continue
            field_lines.append((0, 0, {'model_id': model.id, 'field_id': field.id, 'mode': line.get('mode', 'invisible'),
                                       'mask_start': line.get('mask_start', 2), 'mask_end': line.get('mask_end', 2),
                                       'domain': line.get('domain') or False}))
        for line in item.get('elements', []):
            model = IrModel._get(line.get('model'))
            if not model or not line.get('name'):
                warnings.append(self.env._('%(rule)s: element %(name)s on %(model)s skipped', rule=name,
                                           name=line.get('name'), model=line.get('model')))
                continue
            element_lines.append((0, 0, {'model_id': model.id, 'element_type': line.get('type', 'button'),
                                         'name': line['name']}))
        vals.update(model_line_ids=model_lines, field_line_ids=field_lines, element_line_ids=element_lines)
        Rule = self.env['access.rule'].with_context(active_test=False)
        existing = Rule.search([('name', '=', name)], limit=1)
        try:
            with self.env.cr.savepoint():
                if existing:
                    before = json.dumps(self._serialize(existing)['rules'][0], sort_keys=True, default=str)
                    existing.write(vals)
                    after = json.dumps(self._serialize(existing)['rules'][0], sort_keys=True, default=str)
                    report['updated' if before != after else 'skipped'].append(name)
                else:
                    Rule.create(vals)
                    report['created'].append(name)
        except Exception as exc:  # noqa: BLE001 - report every failing rule, keep importing the others
            report['failed'].append(f'{name}: {exc}')
            return
        report['warnings'].extend(warnings)
