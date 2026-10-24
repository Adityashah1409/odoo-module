import base64
import io

import xlsxwriter

from odoo import api, fields, models
from odoo.fields import Domain

LEVELS = [('full', 'Yes'), ('partial', 'Limited'), ('none', 'No')]
OPERATIONS = ('read', 'write', 'create', 'unlink')
TECHNICAL_PREFIXES = ('ir.', 'base.', 'bus.', 'res.users.', 'web_', 'mail.', 'discuss.', 'auth_', 'iap.', 'digest.',
                      'report.', 'access.', 'spreadsheet.', 'html_editor.', 'web_editor.', 'privacy.', 'sms.',
                      'template.', 'fetchmail.', 'onboarding.', 'snailmail.', 'barcode', 'res.device', 'phone.')


class AccessMap(models.TransientModel):
    _name = 'access.map'
    _description = 'Access map'

    user_id = fields.Many2one('res.users', string='User', domain="[('share', '=', False)]",
                              default=lambda self: self.env.user)
    hide_technical = fields.Boolean('Hide technical models', default=True)
    line_ids = fields.One2many('access.map.line', 'map_id', string='Models')
    line_count = fields.Integer(compute='_compute_line_count')
    xlsx_file = fields.Binary(readonly=True, attachment=False)
    xlsx_name = fields.Char()

    @api.depends('user_id')
    def _compute_display_name(self):
        for wizard in self:
            wizard.display_name = self.env._('Access map: %s', wizard.user_id.name or '')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for wizard in self:
            wizard.line_count = len(wizard.line_ids)

    def _model_level(self, user, model_name, operation):
        """'full', 'partial' or 'none' for ``user`` on the model."""
        Model = self.env[model_name].with_user(user)
        domain = Domain(Model._access_domain(operation)).optimize(Model)
        if domain.is_false():
            return 'none'
        return 'full' if domain.is_true() else 'partial'

    def _areas(self):
        """Module name -> application label (top module category, or the module itself for hidden ones)."""
        modules = self.env['ir.module.module'].sudo().search_fetch([('state', '=', 'installed')],
                                                                  ['name', 'shortdesc', 'category_id'])
        hidden = self.env.ref('base.module_category_hidden', raise_if_not_found=False)
        labels = {}
        for module in modules:
            cat = module.category_id
            while cat.parent_id:
                cat = cat.parent_id
            labels[module.name] = module.shortdesc if not cat or cat == hidden else cat.name
        return labels

    def _defining_modules(self, models):
        """ir.model id -> module that created it (oldest xmlid)."""
        data = self.env['ir.model.data'].sudo().search_fetch(
            [('model', '=', 'ir.model'), ('res_id', 'in', models.ids)], ['module', 'res_id'], order='id')
        result = {}
        for item in data:
            result.setdefault(item.res_id, item.module)
        return result

    def action_compute(self):
        self.ensure_one()
        user = self.user_id or self.env.user
        area_by_module = self._areas()
        restrictions = self.env['access.rule'].sudo()._restrictions_for(user.id, user.company_id.id) or {}
        restricted_models = set(restrictions.get('models', {})) | set(restrictions.get('fields', {})) | \
            set(restrictions.get('elements', {}))
        lines = [(5, 0, 0)]
        ir_models = self.env['ir.model'].sudo().search([('transient', '=', False)], order='model')
        module_of = self._defining_modules(ir_models)
        for model in ir_models:
            name = model.model
            if name not in self.env or self.env[name]._abstract:
                continue
            if self.hide_technical and name.startswith(TECHNICAL_PREFIXES):
                continue
            levels = {op: self._model_level(user, name, op) for op in OPERATIONS}
            if self.hide_technical and all(level == 'none' for level in levels.values()):
                continue
            lines.append((0, 0, {
                'area': area_by_module.get(module_of.get(model.id), self.env._('Other')),
                'model': name, 'model_name': model.name,
                'perm_read': levels['read'], 'perm_write': levels['write'],
                'perm_create': levels['create'], 'perm_unlink': levels['unlink'],
                'managed': name in restricted_models,
            }))
        self.line_ids = lines
        return self._reopen()

    def _reopen(self):
        return {'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'views': [(False, 'form')],
                'target': 'current', 'name': self.env._('Access map')}

    def action_open_lines(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'access.map.line',
            'name': self.env._('Access map: %s', self.user_id.name), 'views': [(False, 'list')],
            'domain': [('map_id', '=', self.id)], 'context': {'search_default_group_area': 1},
        }

    def action_download_xlsx(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_compute()
        buffer = io.BytesIO()
        book = xlsxwriter.Workbook(buffer, {'in_memory': True})
        sheet = book.add_worksheet(self.env._('Access map'))
        head = book.add_format({'bold': True, 'bg_color': '#714B67', 'font_color': '#FFFFFF', 'border': 1})
        area_fmt = book.add_format({'bold': True, 'bg_color': '#EDE7EC'})
        formats = {
            'full': book.add_format({'bg_color': '#D1F2DC', 'align': 'center', 'border': 1}),
            'partial': book.add_format({'bg_color': '#FFF1C2', 'align': 'center', 'border': 1}),
            'none': book.add_format({'bg_color': '#F8D7DA', 'align': 'center', 'border': 1}),
        }
        labels = dict(LEVELS)
        sheet.write_row(0, 0, [self.env._('Application'), self.env._('Model'), self.env._('Technical name'),
                               self.env._('Read'), self.env._('Write'), self.env._('Create'), self.env._('Delete'),
                               self.env._('Access rule')], head)
        sheet.set_column(0, 0, 18)
        sheet.set_column(1, 2, 32)
        sheet.set_column(3, 6, 10)
        sheet.set_column(7, 7, 12)
        row = 1
        current_area = None
        for line in self.line_ids.sorted(lambda l: (l.area or '', l.model)):
            if line.area != current_area:
                current_area = line.area
                sheet.merge_range(row, 0, row, 7, current_area, area_fmt)
                row += 1
            sheet.write(row, 0, line.area)
            sheet.write(row, 1, line.model_name)
            sheet.write(row, 2, line.model)
            for col, value in enumerate((line.perm_read, line.perm_write, line.perm_create, line.perm_unlink), 3):
                sheet.write(row, col, labels[value], formats[value])
            sheet.write(row, 7, self.env._('Yes') if line.managed else '')
            row += 1
        sheet.freeze_panes(1, 0)
        sheet.autofilter(0, 0, max(row - 1, 1), 7)
        book.close()
        name = 'access_map_%s.xlsx' % (self.user_id.login or 'user').replace('@', '_')
        self.write({'xlsx_file': base64.b64encode(buffer.getvalue()).decode(), 'xlsx_name': name})
        return {
            'type': 'ir.actions.act_url', 'target': 'download',
            'url': f'/web/content/access.map/{self.id}/xlsx_file/{name}?download=true',
        }


class AccessMapLine(models.TransientModel):
    _name = 'access.map.line'
    _description = 'Access map line'
    _order = 'area, model'

    map_id = fields.Many2one('access.map', required=True, ondelete='cascade', index=True)
    area = fields.Char('Application')
    model = fields.Char('Technical name')
    model_name = fields.Char('Model')
    perm_read = fields.Selection(LEVELS, string='Read')
    perm_write = fields.Selection(LEVELS, string='Write')
    perm_create = fields.Selection(LEVELS, string='Create')
    perm_unlink = fields.Selection(LEVELS, string='Delete')
    managed = fields.Boolean('Access rule', help='An access rule of this module changes this model for the user.')
