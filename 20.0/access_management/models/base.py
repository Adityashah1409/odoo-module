from lxml import etree

from odoo import api, models
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.safe_eval import safe_eval

from .access_rule_lines import mask_value

X2MANY_SUBVIEWS = ('list', 'form', 'kanban', 'tree')


def _direct_rpc(model_name, *methods):
    """True when the current HTTP request is a direct call of ``methods`` on ``model_name`` (web client / RPC)."""
    try:
        params = request and request.params
    except RuntimeError:
        return False
    return bool(params) and params.get('model') == model_name and params.get('method') in methods


class Base(models.AbstractModel):
    _inherit = 'base'

    # ------------------------------------------------------------------ helpers
    @api.model
    def _am_restrictions(self):
        return self.env['access.rule']._get_restrictions()

    @api.model
    def _am_raise(self, message):
        raise AccessError(self.env._('%(message)s\n\n(Restricted by Access Management.)', message=message))

    # ------------------------------------------------------------------ views
    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        result = super().get_view(view_id, view_type, **options)
        restrictions = self._am_restrictions()
        if restrictions and (restrictions['models'] or restrictions['fields'] or restrictions['elements']
                             or restrictions['readonly_user']):
            node = etree.fromstring(result['arch'])
            self._am_process_arch(node, self._name, view_type, restrictions, root=True)
            result = dict(result, arch=etree.tostring(node, encoding='unicode'))
        return result

    @api.model
    def _am_process_arch(self, node, model_name, view_type, restrictions, root=False):
        info = restrictions['models'].get(model_name) or {}
        Model = self.env.get(model_name)
        readonly_user = restrictions['readonly_user'] and Model is not None and not Model._transient \
            and not model_name.startswith(('ir.', 'res.users', 'mail.', 'bus.', 'access.'))
        if root or node.tag in X2MANY_SUBVIEWS:
            if info.get('no_create') or 'create' in info.get('ops', ()) or readonly_user:
                node.set('create', '0')
            if 'write' in info.get('ops', ()) or readonly_user:
                node.set('edit', '0')
            if 'unlink' in info.get('ops', ()) or readonly_user:
                node.set('delete', '0')
            if info.get('no_duplicate') or readonly_user:
                node.set('duplicate', '0')
            if info.get('no_import') or readonly_user:
                node.set('import', '0')
            if info.get('no_export'):
                node.set('export_xlsx', '0')
        if view_type == 'search' and root:
            for flag, xpath in (('hide_filters', ".//filter[not(@context) or not(contains(@context, 'group_by'))]"),
                                ('hide_group_by', ".//filter[contains(@context, 'group_by')]"),
                                ('hide_search_panel', './/searchpanel')):
                if info.get(flag):
                    for element in node.xpath(xpath):
                        element.getparent().remove(element)
            return
        fields_rules = restrictions['fields'].get(model_name, {})
        elements = restrictions['elements'].get(model_name, {})
        hidden_buttons, hidden_pages = elements.get('button', ()), elements.get('page', ())
        if root and node.tag == 'form':
            self._am_process_chatter(node, info)
        for child in list(node):
            if not isinstance(child.tag, str):
                continue
            if child.tag == 'field':
                fname = child.get('name')
                rule = fields_rules.get(fname)
                if rule:
                    if rule['mode'] == 'invisible':
                        child.set('invisible', '1')
                        if node.tag == 'list':
                            child.set('column_invisible', '1')
                    elif rule['mode'] in ('readonly', 'mask'):
                        child.set('readonly', '1')
                    elif rule['mode'] == 'required':
                        child.set('required', '1')
                field = Model._fields.get(fname) if Model is not None else None
                if field is not None and field.type in ('one2many', 'many2many') and len(child):
                    for sub in child:
                        if isinstance(sub.tag, str) and sub.tag in X2MANY_SUBVIEWS:
                            self._am_process_arch(sub, field.comodel_name, sub.tag, restrictions, root=False)
                    continue
            elif child.tag == 'button' and child.get('name') in hidden_buttons:
                child.set('invisible', '1')
                continue
            elif child.tag == 'page' and child.get('name') in hidden_pages:
                child.set('invisible', '1')
            self._am_process_arch(child, model_name, view_type, restrictions)

    @api.model
    def _am_process_chatter(self, node, info):
        if info.get('hide_chatter'):
            for chatter in node.xpath('.//chatter | .//div[hasclass("oe_chatter")]'):
                chatter.getparent().remove(chatter)
            return
        classes = [name for flag, name in (
            ('hide_send_message', 'o_am_hide_send'), ('hide_log_note', 'o_am_hide_log'),
            ('hide_activities', 'o_am_hide_activities'), ('hide_followers', 'o_am_hide_followers'),
            ('hide_attachments', 'o_am_hide_attachments')) if info.get(flag)]
        if classes and node.xpath('.//chatter'):
            # a marker inside the form; the stylesheet hides the matching chatter controls
            marker = etree.SubElement(node, 'div', {'class': 'd-none o_am_chatter_marker ' + ' '.join(classes)})
            sheet = node.find('sheet')
            if sheet is not None:
                node.remove(marker)
                sheet.append(marker)

    @api.model
    def get_views(self, views, options=None):
        result = super().get_views(views, options)
        restrictions = self._am_restrictions()
        if not restrictions:
            return result
        info = restrictions['models'].get(self._name) or {}
        for view in result['views'].values():
            toolbar = view.get('toolbar')
            if not toolbar or not info:
                continue
            if info.get('hide_all_reports'):
                toolbar.pop('print', None)
            elif info.get('report_ids') and 'print' in toolbar:
                toolbar['print'] = [a for a in toolbar['print'] if a['id'] not in info['report_ids']]
            if info.get('hide_all_actions'):
                toolbar.pop('action', None)
            elif info.get('action_ids') and 'action' in toolbar:
                toolbar['action'] = [a for a in toolbar['action'] if a['id'] not in info['action_ids']]
        model_info = result.get('models', {}).get(self._name, {})
        if info.get('no_archive') and 'active' in model_info.get('fields', {}):
            model_info['fields']['active']['readonly'] = True
        return result

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        result = super().fields_get(allfields, attributes)
        restrictions = self._am_restrictions()
        rules = restrictions and restrictions['fields'].get(self._name)
        if not rules:
            return result
        for fname, rule in rules.items():
            description = result.get(fname)
            if description is None:
                continue
            if rule['mode'] in ('readonly', 'mask') and (attributes is None or 'readonly' in attributes):
                description['readonly'] = True
            if rule['mode'] == 'required' and (attributes is None or 'required' in attributes):
                description['required'] = True
            if rule['mode'] in ('invisible', 'mask') and (attributes is None or 'exportable' in attributes):
                description['exportable'] = False
        return result

    # ------------------------------------------------------------------ data
    def web_read(self, specification):
        result = super().web_read(specification)
        restrictions = self._am_restrictions()
        rules = restrictions and restrictions['fields'].get(self._name)
        if rules and result:
            self._am_mask_rows(result, rules, specification)
        return result

    def _am_mask_rows(self, rows, rules, names):
        masked = self._am_masked_names(rules, names)
        if not masked:
            return
        context = self.env['access.rule']._eval_context()
        for fname, rule in masked.items():
            ids = None
            if rule['domain']:
                ids = set(self.sudo().filtered_domain(safe_eval(rule['domain'], context)).ids)
            for row in rows:
                if ids is None or row.get('id') in ids:
                    row[fname] = mask_value(row.get(fname), rule['start'], rule['end'])

    def _am_masked_names(self, rules, names):
        """{name: rule} for the masked fields among ``names`` and their companions
        (phone_sanitized, phone_formatted, email_normalized, email_formatted...)."""
        masked = {}
        for fname, rule in rules.items():
            if rule['mode'] != 'mask':
                continue
            for name in names:
                field = self._fields.get(name)
                if (name == fname or name.startswith(fname + '_')) and field is not None \
                        and field.type in ('char', 'text'):
                    masked[name] = rule
        return masked

    def web_save(self, vals, specification, next_id=None):
        self._am_check_field_write(vals)
        return super().web_save(vals, specification, next_id=next_id)

    def write(self, vals):
        if not self.env.su and _direct_rpc(self._name, 'write'):
            self._am_check_field_write(vals)
        return super().write(vals)

    def _am_check_field_write(self, vals):
        restrictions = self._am_restrictions()
        rules = restrictions and restrictions['fields'].get(self._name)
        if not rules or not self:
            return
        locked = [fname for fname in vals if fname in rules and rules[fname]['mode'] in ('readonly', 'mask')]
        if locked:
            labels = ', '.join(self._fields[f].string for f in locked if f in self._fields)
            self._am_raise(self.env._('You cannot change these fields: %s.', labels))

    def copy(self, default=None):
        if not self.env.su and _direct_rpc(self._name, 'copy'):
            info = self.env['access.rule']._model_restrictions(self._name)
            if info and info.get('no_duplicate'):
                self._am_raise(self.env._('You cannot duplicate these records.'))
        return super().copy(default=default)

    def action_archive(self):
        self._am_check_archive()
        return super().action_archive()

    def action_unarchive(self):
        self._am_check_archive()
        return super().action_unarchive()

    def _am_check_archive(self):
        if self.env.su:
            return
        info = self.env['access.rule']._model_restrictions(self._name)
        if info and info.get('no_archive'):
            self._am_raise(self.env._('You cannot archive or restore these records.'))

    def export_data(self, fields_to_export):
        if self.env.su:
            return super().export_data(fields_to_export)
        info = self.env['access.rule']._model_restrictions(self._name)
        if info and info.get('no_export'):
            self._am_raise(self.env._('You cannot export these records.'))
        result = super().export_data(fields_to_export)
        restrictions = self._am_restrictions()
        rules = restrictions and restrictions['fields'].get(self._name)
        if rules:
            companions = self._am_masked_names(rules, fields_to_export)
            masked = {i: companions.get(name) or rules[name] for i, name in enumerate(fields_to_export)
                      if name in companions or (name in rules and rules[name]['mode'] == 'invisible')}
            for row in result.get('datas', []):
                for index, rule in masked.items():
                    if index < len(row):
                        row[index] = '' if rule['mode'] == 'invisible' else \
                            mask_value(row[index], rule['start'], rule['end'])
        if self._name != 'access.export.log' and not self.env.context.get('access_management_no_log'):
            self.env['access.export.log'].sudo()._log_export(self, fields_to_export)
        return result

    @api.model
    def load(self, fields, data):
        if not self.env.su:
            info = self.env['access.rule']._model_restrictions(self._name)
            if info and info.get('no_import'):
                self._am_raise(self.env._('You cannot import these records.'))
        return super().load(fields, data)
