from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

TECHNICAL_MODEL_DOMAIN = "[('transient', '=', False), ('model', 'not like', 'access.%'), ('model', 'not like', 'ir.%'), " \
                         "('model', 'not like', 'bus.%'), ('model', 'not like', 'base.%')]"


class AccessRuleLineMixin(models.AbstractModel):
    _name = 'access.rule.line.mixin'
    _description = 'Access rule line: cache invalidation'

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        self.env.registry.clear_cache()
        return lines

    def write(self, vals):
        res = super().write(vals)
        self.env.registry.clear_cache()
        return res

    def unlink(self):
        res = super().unlink()
        self.env.registry.clear_cache()
        return res


class AccessRuleModel(models.Model):
    _name = 'access.rule.model'
    _inherit = ['access.rule.line.mixin']
    _description = 'Access Rule: model'
    _order = 'rule_id, id'

    rule_id = fields.Many2one('access.rule', required=True, ondelete='cascade', index=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade',
                               domain=TECHNICAL_MODEL_DOMAIN)
    model = fields.Char(related='model_id.model', string='Technical name')

    readonly = fields.Boolean('Read-only', help='No create, edit, delete, duplicate, archive or import.')
    no_create = fields.Boolean('No create')
    no_edit = fields.Boolean('No edit')
    no_delete = fields.Boolean('No delete')
    no_duplicate = fields.Boolean('No duplicate')
    no_archive = fields.Boolean('No archive')
    no_import = fields.Boolean('No import')
    no_export = fields.Boolean('No export')
    domain = fields.Char('Only records', help='Records outside this domain are invisible and cannot be changed. '
                                              'Use user, company_id and company_ids, e.g. '
                                              '[("user_id", "=", user.id)].')

    hide_chatter = fields.Boolean('Hide chatter')
    hide_send_message = fields.Boolean('Hide "Send message"')
    hide_log_note = fields.Boolean('Hide "Log note"')
    hide_activities = fields.Boolean('Hide activities')
    hide_followers = fields.Boolean('Hide followers')
    hide_attachments = fields.Boolean('Hide attachments')

    hide_all_reports = fields.Boolean('Hide all reports')
    report_ids = fields.Many2many('ir.actions.report', string='Hidden reports',
                                  domain="[('model', '=', model)]")
    hide_all_actions = fields.Boolean('Hide all actions')
    action_ids = fields.Many2many('ir.actions.server', string='Hidden actions',
                                  domain="[('binding_model_id', '=', model_id)]")
    window_action_ids = fields.Many2many('ir.actions.act_window', string='Hidden wizards',
                                         domain="[('binding_model_id', '=', model_id)]")

    hide_search_panel = fields.Boolean('Hide search panel')
    hide_filters = fields.Boolean('Hide filters')
    hide_group_by = fields.Boolean('Hide group by')

    summary = fields.Char(compute='_compute_summary')

    @api.depends('readonly', 'no_create', 'no_edit', 'no_delete', 'no_duplicate', 'no_archive', 'no_import',
                 'no_export', 'domain', 'hide_chatter', 'hide_send_message', 'hide_log_note', 'hide_activities',
                 'hide_followers', 'hide_attachments', 'hide_all_reports', 'report_ids', 'hide_all_actions',
                 'action_ids', 'window_action_ids', 'hide_search_panel', 'hide_filters', 'hide_group_by')
    def _compute_summary(self):
        labels = self._fields
        for line in self:
            parts = [labels[name].string for name in (
                'readonly', 'no_create', 'no_edit', 'no_delete', 'no_duplicate', 'no_archive', 'no_import',
                'no_export', 'hide_chatter', 'hide_send_message', 'hide_log_note', 'hide_activities',
                'hide_followers', 'hide_attachments', 'hide_all_reports', 'hide_all_actions', 'hide_search_panel',
                'hide_filters', 'hide_group_by') if line[name]]
            if line.report_ids and not line.hide_all_reports:
                parts.append(self.env._('%s report(s) hidden', len(line.report_ids)))
            if (line.action_ids or line.window_action_ids) and not line.hide_all_actions:
                parts.append(self.env._('%s action(s) hidden', len(line.action_ids) + len(line.window_action_ids)))
            if line.domain and line.domain.strip() not in ('', '[]'):
                parts.append(self.env._('domain'))
            line.summary = ', '.join(parts)

    @api.constrains('domain')
    def _check_domain(self):
        context = self.env['access.rule']._eval_context()
        for line in self.filtered('domain'):
            try:
                domain = safe_eval(line.domain, context)
                self.env[line.model_id.model].sudo().search_count(domain, limit=1)
            except Exception as exc:
                raise ValidationError(self.env._('Invalid domain on %(model)s: %(error)s',
                                                 model=line.model_id.name, error=exc)) from exc

    @api.onchange('readonly')
    def _onchange_readonly(self):
        if self.readonly:
            self.update(dict.fromkeys(('no_create', 'no_edit', 'no_delete', 'no_duplicate', 'no_archive',
                                       'no_import'), True))


class AccessRuleField(models.Model):
    _name = 'access.rule.field'
    _inherit = ['access.rule.line.mixin']
    _description = 'Access Rule: field'
    _order = 'rule_id, model_id, id'

    rule_id = fields.Many2one('access.rule', required=True, ondelete='cascade', index=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade',
                               domain=TECHNICAL_MODEL_DOMAIN)
    model = fields.Char(related='model_id.model', string='Technical name')
    field_id = fields.Many2one('ir.model.fields', string='Field', required=True, ondelete='cascade',
                               domain="[('model_id', '=', model_id), ('name', 'not in', ('id', 'display_name'))]")
    mode = fields.Selection([
        ('invisible', 'Hidden'),
        ('readonly', 'Read-only'),
        ('required', 'Required'),
        ('mask', 'Masked'),
    ], required=True, default='invisible')
    mask_start = fields.Integer('Show first', default=2, help='Characters kept at the start.')
    mask_end = fields.Integer('Show last', default=2, help='Characters kept at the end.')
    domain = fields.Char('Only for records', help='Mask only the records matching this domain (empty: all).')
    preview = fields.Char(compute='_compute_preview')

    @api.depends('mode', 'mask_start', 'mask_end', 'field_id')
    def _compute_preview(self):
        for line in self:
            line.preview = mask_value('jane.doe@example.com' if line.field_id.name and 'mail' in line.field_id.name
                                      else '+44 7700 900123', line.mask_start, line.mask_end) \
                if line.mode == 'mask' else False

    @api.onchange('model_id')
    def _onchange_model_id(self):
        if self.field_id and self.field_id.model_id != self.model_id:
            self.field_id = False

    @api.constrains('mode', 'field_id')
    def _check_mask(self):
        for line in self.filtered(lambda l: l.mode == 'mask'):
            if line.field_id.ttype not in ('char', 'text'):
                raise ValidationError(self.env._('Only text fields can be masked (%s).', line.field_id.field_description))
            if line.mask_start < 0 or line.mask_end < 0:
                raise ValidationError(self.env._('The visible characters cannot be negative.'))


class AccessRuleElement(models.Model):
    _name = 'access.rule.element'
    _inherit = ['access.rule.line.mixin']
    _description = 'Access Rule: button or tab'
    _order = 'rule_id, model_id, id'

    rule_id = fields.Many2one('access.rule', required=True, ondelete='cascade', index=True)
    model_id = fields.Many2one('ir.model', string='Model', required=True, ondelete='cascade',
                               domain=TECHNICAL_MODEL_DOMAIN)
    model = fields.Char(related='model_id.model', string='Model technical name')
    element_type = fields.Selection([('button', 'Button'), ('page', 'Tab')], string='Type', required=True,
                                    default='button')
    name = fields.Char('Technical name', required=True,
                       help='The name attribute of the button (method or action) or of the notebook page.')
    label = fields.Char(compute='_compute_label', string='Label')
    available = fields.Text(compute='_compute_available', string='Found in the views')

    @api.depends('model_id', 'element_type', 'name')
    def _compute_label(self):
        for line in self:
            found = dict(line._scan_elements()) if line.model_id and line.name else {}
            line.label = found.get(line.name.strip()) if line.name else False

    @api.depends('model_id', 'element_type')
    def _compute_available(self):
        for line in self:
            elements = line._scan_elements() if line.model_id else []
            line.available = '\n'.join(f'{name}  ·  {label}' for name, label in elements) or False

    def _scan_elements(self):
        """(name, label) of the buttons or pages of the model's form, list and kanban views."""
        self.ensure_one()
        model = self.env.get(self.model_id.model)
        if model is None:
            return []
        found = {}
        for view_type in ('form', 'list', 'kanban'):
            try:
                arch = model.sudo().with_context(access_management_raw=True)._get_view_cache(view_type=view_type)['arch']
            except Exception:  # noqa: BLE001 - a model may have no such view
                continue
            node = etree.fromstring(arch)
            tag = 'button' if self.element_type == 'button' else 'page'
            for element in node.iter(tag):
                name = element.get('name')
                if name and name not in found:
                    label = element.get('string') or element.get('title') or \
                        ' '.join(''.join(element.itertext()).split())[:60]
                    found[name] = label or name
        return sorted(found.items())


def mask_value(value, start, end, char='•'):
    """'+44 7700 900123' -> '+4•••••••••••23' (spaces and @ kept to stay readable)."""
    if not value or not isinstance(value, str):
        return value
    length = len(value)
    if start + end >= length:
        start, end = min(start, max(length - 1, 0)), 0
    head, body, tail = value[:start], value[start:length - end if end else length], value[length - end:] if end else ''
    if '@' in value and '@' in body:  # e-mails: keep the domain shape
        local, _sep, domain = body.partition('@')
        return head + char * len(local) + '@' + domain[:1] + char * max(len(domain) - 1, 0) + tail
    return head + ''.join(c if c in ' -.' else char for c in body) + tail
