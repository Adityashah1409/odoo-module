import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class CloudStorageRule(models.Model):
    _name = 'cloud.storage.rule'
    _description = 'Cloud Storage Folder Rule'
    _parent_store = True
    _order = 'sequence, id'

    name = fields.Char(required=True, help="Also the name of the container folder.")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    client_id = fields.Many2one('cloud.storage.client', required=True, ondelete='cascade',
                                compute='_compute_client_id', store=True, readonly=False, precompute=True,
                                recursive=True)
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade',
                               domain=[('transient', '=', False)])
    model_name = fields.Char(related='model_id.model', string="Model name", store=True)
    domain = fields.Char(default='[]', required=True,
                         help="Only records matching this filter get a folder.")
    name_expression = fields.Char(
        default='record.display_name', required=True,
        help="Python expression giving the folder name; `record` is the Odoo record.")
    parent_id = fields.Many2one('cloud.storage.rule', string="Parent rule", ondelete='cascade', index=True,
                                help="Create these folders inside the folders of the parent rule.")
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('cloud.storage.rule', 'parent_id')
    parent_field_id = fields.Many2one(
        'ir.model.fields', string="Link to parent record", ondelete='cascade',
        domain="[('model_id', '=', model_id), ('ttype', '=', 'many2one')]",
        help="Many2one field of this model that points to the parent rule's record.")
    subfolder_names = fields.Char(
        string="Default subfolders",
        help="Comma separated, created in every record folder (e.g. Contracts, Photos).")
    max_folders = fields.Integer(default=500, help="Maximum number of record folders for this rule.")
    folder_ids = fields.One2many('cloud.storage.folder', 'rule_id')
    folder_count = fields.Integer(compute='_compute_folder_count')

    @api.depends('parent_id.client_id')
    def _compute_client_id(self):
        for rule in self:
            if rule.parent_id:
                rule.client_id = rule.parent_id.client_id

    def _compute_folder_count(self):
        counts = dict(self.env['cloud.storage.folder']._read_group(
            [('rule_id', 'in', self.ids), ('res_model', '!=', False)], ['rule_id'], ['__count']))
        for rule in self:
            rule.folder_count = counts.get(rule, 0)

    @api.constrains('parent_id', 'parent_field_id', 'model_id', 'domain', 'name_expression')
    def _check_rule(self):
        if self._has_cycle():
            raise ValidationError(_("A rule cannot be its own parent."))
        for rule in self:
            if rule.parent_id:
                if not rule.parent_field_id:
                    raise ValidationError(_("Rule %s needs the field that links it to the parent record.", rule.name))
                if rule.parent_field_id.relation != rule.parent_id.model_name:
                    raise ValidationError(_(
                        "Field %(field)s must point to %(model)s.",
                        field=rule.parent_field_id.name, model=rule.parent_id.model_name))
            try:
                domain = safe_eval(rule.domain or '[]')
                self.env[rule.model_name].search_count(domain, limit=1)
            except Exception as e:  # noqa: BLE001
                raise ValidationError(_("Invalid filter on rule %(name)s: %(error)s", name=rule.name, error=e)) from e

    def action_view_folders(self):
        action = self.env['ir.actions.act_window']._for_xml_id('cloud_storage_sync.action_cloud_storage_folder')
        action['domain'] = [('rule_id', '=', self.id)]
        return action

    def action_generate(self):
        self._generate_folders()
        return True

    # ------------------------------------------------------------------
    # Folder generation
    # ------------------------------------------------------------------
    def _folder_name(self, record):
        self.ensure_one()
        try:
            name = safe_eval(self.name_expression, {'record': record})
        except Exception:  # noqa: BLE001
            _logger.warning("Folder name expression failed on rule %s", self.id, exc_info=True)
            name = record.display_name
        return str(name or record.display_name or record.id)

    def _ensure_folder(self, parent, name, record=None, existing=None):
        """Return the folder for `record` (or the container named `name`) under `parent`."""
        Folder = self.env['cloud.storage.folder'].sudo()
        folder = existing
        if folder is None:
            domain = [('rule_id', '=', self.id), ('parent_id', '=', parent.id if parent else False)]
            if record is not None:
                domain = [('res_model', '=', record._name), ('res_id', '=', record.id)]
            else:
                domain += [('res_model', '=', False), ('name', '=', name)]
            folder = Folder.with_context(active_test=False).search(domain, limit=1)
        values = {'name': name, 'parent_id': parent.id if parent else False, 'client_id': self.client_id.id,
                  'rule_id': self.id, 'manual': False, 'active': True}
        if record is not None:
            values.update(res_model=record._name, res_id=record.id)
        if folder:
            changes = {k: v for k, v in values.items()
                       if (folder[k].id if hasattr(folder[k], 'id') else folder[k]) != v}
            if changes:
                folder.write(changes)
        else:
            folder = Folder.create(values)
        return folder

    def _ensure_subfolders(self, folder):
        Folder = self.env['cloud.storage.folder'].sudo()
        existing = set(folder.child_ids.mapped('name'))
        for name in [n.strip() for n in (self.subfolder_names or '').split(',') if n.strip()]:
            if name not in existing:
                Folder.create({'name': name, 'parent_id': folder.id, 'client_id': self.client_id.id,
                               'rule_id': self.id, 'manual': False})

    def _records(self, extra_domain=None):
        domain = safe_eval(self.domain or '[]') + (extra_domain or [])
        return self.env[self.model_name].sudo().search(domain, limit=self.max_folders or None)

    def _generate_folders(self):
        """Create, rename, move and retire the folders produced by these rules."""
        rules = self.filtered(lambda r: r.active and r.client_id.state in ('confirmed', 'draft'))
        # parents before children
        for rule in rules.sorted(lambda r: (r.parent_path or '', r.sequence)):
            keep = self.env['cloud.storage.folder']
            if not rule.parent_id:
                container = rule._ensure_folder(False, rule.name)
                keep |= container
                for record in rule._records():
                    folder = rule._ensure_folder(container, rule._folder_name(record), record)
                    rule._ensure_subfolders(folder)
                    keep |= folder
            else:
                parent_folders = rule.parent_id.folder_ids.filtered(lambda f: f.res_model and f.active)
                for parent_folder in parent_folders:
                    children = rule._records([(rule.parent_field_id.name, '=', parent_folder.res_id)])
                    if not children:
                        continue
                    container = rule._ensure_folder(parent_folder, rule.name)
                    keep |= container
                    for record in children:
                        folder = rule._ensure_folder(container, rule._folder_name(record), record)
                        rule._ensure_subfolders(folder)
                        keep |= folder
            rule._retire_folders(keep)

    def _retire_folders(self, keep):
        """Folders that no longer match: files come back to Odoo, folder is archived."""
        self.ensure_one()
        candidates = self.env['cloud.storage.folder'].sudo().search([
            ('rule_id', '=', self.id), ('id', 'not in', keep.ids)])
        # default subfolders of kept folders stay; descendants of obsolete folders follow their parent
        obsolete = candidates.filtered(
            lambda f: f.parent_id not in candidates and (f.res_model or f.parent_id not in keep))
        if not obsolete:
            return
        Queue = self.env['cloud.storage.queue'].sudo()
        all_folders = self.env['cloud.storage.folder'].sudo().search([('id', 'child_of', obsolete.ids)])
        files = self.env['ir.attachment'].sudo().search([('cloud_folder_id', 'in', all_folders.ids)])
        for attachment in files.filtered(lambda a: a.type == 'url' and a.cloud_state == 'synced'):
            Queue._enqueue('pull', self.client_id, attachment=attachment, priority=1)
        files.with_context(cloud_storage_skip_sync=True).write({'cloud_folder_id': False})
        for folder in obsolete.filtered(lambda f: f.sync_state == 'synced'):
            Queue._enqueue('delete', self.client_id, path=folder.remote_path, priority=20)
        all_folders.with_context(cloud_storage_skip_sync=True).write({'active': False, 'sync_state': 'pending'})
        self.client_id._log(_("%(count)s folder(s) of rule %(rule)s no longer match and were archived.",
                              count=len(obsolete), rule=self.name))

    @api.model
    def _cron_generate_folders(self):
        self.search([])._generate_folders()
