import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .providers import join_path

INVALID_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def sanitize(name):
    name = INVALID_CHARS.sub('-', name or '').strip(' .')
    return name[:200] or '-'


class CloudStorageFolder(models.Model):
    _name = 'cloud.storage.folder'
    _description = 'Cloud Storage Folder'
    _parent_store = True
    _order = 'complete_name, id'
    _rec_name = 'complete_name'

    name = fields.Char(required=True)
    complete_name = fields.Char(compute='_compute_complete_name', store=True, recursive=True)
    sanitized_name = fields.Char(compute='_compute_paths', store=True, recursive=True)
    remote_path = fields.Char(
        compute='_compute_paths', store=True, recursive=True,
        help="Path of the folder inside the client root.")
    active = fields.Boolean(default=True)
    parent_id = fields.Many2one('cloud.storage.folder', ondelete='cascade', index=True)
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('cloud.storage.folder', 'parent_id')
    client_id = fields.Many2one(
        'cloud.storage.client', ondelete='cascade', index=True,
        compute='_compute_client_id', store=True, readonly=False, recursive=True)

    rule_id = fields.Many2one('cloud.storage.rule', ondelete='set null', index=True, readonly=True)
    res_model = fields.Char("Linked model", index=True, readonly=True)
    res_id = fields.Many2oneReference("Linked record", model_field='res_model', index=True, readonly=True)
    manual = fields.Boolean(default=True, readonly=True,
                            help="Created by a user (or found in the storage), not by a folder rule.")
    user_ids = fields.Many2many('res.users', string="Restricted to users",
                                help="Leave empty with no groups to give access to every file manager user.")
    group_ids = fields.Many2many('res.groups', string="Restricted to groups")

    sync_state = fields.Selection(
        [('pending', 'Waiting'), ('synced', 'Synced'), ('error', 'Error')],
        default='pending', readonly=True, copy=False)
    last_backward_check = fields.Datetime(readonly=True, copy=False)
    attachment_ids = fields.One2many('ir.attachment', 'cloud_folder_id', string="Files")
    attachment_count = fields.Integer(compute='_compute_attachment_count')

    _unique_record = models.UniqueIndex(
        '(res_model, res_id) WHERE res_model IS NOT NULL AND active',
        "A record can only have one folder.")

    @api.constrains('parent_id')
    def _check_parent(self):
        if self._has_cycle():
            raise ValidationError(_("A folder cannot be its own ancestor."))

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for folder in self:
            folder.complete_name = (f"{folder.parent_id.complete_name} / {folder.name}"
                                    if folder.parent_id else folder.name)

    @api.depends('name', 'parent_id.remote_path')
    def _compute_paths(self):
        for folder in self:
            folder.sanitized_name = sanitize(folder.name)
            folder.remote_path = join_path(folder.parent_id.remote_path, folder.sanitized_name)

    @api.depends('parent_id.client_id')
    def _compute_client_id(self):
        for folder in self:
            if folder.parent_id:
                folder.client_id = folder.parent_id.client_id

    def _compute_attachment_count(self):
        counts = dict(self.env['ir.attachment']._read_group(
            [('cloud_folder_id', 'in', self.ids)], ['cloud_folder_id'], ['__count']))
        for folder in self:
            folder.attachment_count = counts.get(folder, 0)

    # ------------------------------------------------------------------
    # CRUD: keep the storage in line
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        folders = super().create(vals_list)
        if not self.env.context.get('cloud_storage_skip_sync'):
            folders._enqueue_mkdir()
        return folders

    def write(self, vals):
        moving = self.browse()
        if not self.env.context.get('cloud_storage_skip_sync') and ({'name', 'parent_id'} & set(vals)):
            moving = self.filtered(lambda f: f.sync_state == 'synced')
            old_paths = {f.id: f.remote_path for f in moving}
        result = super().write(vals)
        Queue = self.env['cloud.storage.queue'].sudo()
        for folder in moving:
            if old_paths[folder.id] != folder.remote_path and folder.client_id:
                Queue._enqueue('move', folder.client_id, folder=folder,
                               path=old_paths[folder.id], new_path=folder.remote_path)
        if 'client_id' in vals and not self.env.context.get('cloud_storage_skip_sync'):
            self.filtered(lambda f: f.sync_state != 'synced')._enqueue_mkdir()
        return result

    def unlink(self):
        if not self.env.context.get('cloud_storage_skip_sync'):
            files = self.env['ir.attachment'].sudo().search([
                ('cloud_folder_id', 'child_of', self.ids), ('cloud_state', '=', 'synced'), ('type', '=', 'url')])
            if files:
                raise UserError(_(
                    "Some files of these folders only exist in the cloud. Pull them back "
                    "(client > Pull files back) or archive the folders instead."))
        return super().unlink()

    def _enqueue_mkdir(self):
        Queue = self.env['cloud.storage.queue'].sudo()
        for folder in self.filtered('client_id'):
            Queue._enqueue('mkdir', folder.client_id, folder=folder, priority=5)

    def _attachment_target(self):
        """(res_model, res_id) for a file placed in this folder."""
        self.ensure_one()
        if self.res_model and self.res_id:
            return self.res_model, self.res_id
        return self._name, self.id

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_open_record(self):
        self.ensure_one()
        if not self.res_model:
            raise UserError(_("This folder is not linked to a record."))
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model,
                'res_id': self.res_id, 'views': [(False, 'form')]}

    def action_view_files(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('cloud_storage_sync.action_cloud_storage_files')
        action['domain'] = [('cloud_folder_id', 'child_of', self.id)]
        action['context'] = {'default_cloud_folder_id': self.id, 'searchpanel_default_cloud_folder_id': self.id}
        return action

    def action_open_in_cloud(self):
        self.ensure_one()
        url = self.client_id._provider().public_url(self.client_id._full_path(self.remote_path))
        if not url:
            raise UserError(_("Set a browser base URL on the client to open folders in the cloud."))
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}

    def action_download_zip(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': f'/cloud_storage_sync/folder/{self.id}/zip'}
