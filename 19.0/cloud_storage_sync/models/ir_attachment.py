from odoo import api, fields, models

from .cloud_storage_folder import sanitize


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    cloud_folder_id = fields.Many2one('cloud.storage.folder', string="Folder", index='btree_not_null',
                                      ondelete='set null')
    cloud_client_id = fields.Many2one(related='cloud_folder_id.client_id', string="Cloud client")
    cloud_path = fields.Char("Cloud path", readonly=True, copy=False)
    cloud_state = fields.Selection(
        [('local', 'Only in Odoo'), ('queued', 'Waiting for sync'), ('synced', 'In the cloud'),
         ('missing', 'Missing in the cloud'), ('error', 'Sync error')],
        default='local', readonly=True, copy=False)
    cloud_mimetype = fields.Char(readonly=True, copy=False)

    # ------------------------------------------------------------------
    # Folder assignment
    # ------------------------------------------------------------------
    @api.model
    def _cloud_folders_for(self, pairs):
        """{(res_model, res_id): folder} for the given record references."""
        pairs = {(m, i) for m, i in pairs if m and i}
        if not pairs:
            return {}
        Folder = self.env['cloud.storage.folder'].sudo()
        result = {}
        folder_ids = [i for m, i in pairs if m == Folder._name]
        for folder in Folder.browse(folder_ids).exists():
            result[(Folder._name, folder.id)] = folder
        others = {(m, i) for m, i in pairs if m != Folder._name}
        if others:
            folders = Folder.search([('res_model', 'in', list({m for m, _i in others})),
                                     ('res_id', 'in', list({i for _m, i in others}))])
            for folder in folders:
                if (folder.res_model, folder.res_id) in others:
                    result[(folder.res_model, folder.res_id)] = folder
        return result

    @api.model_create_multi
    def create(self, vals_list):
        skip = self.env.context.get('cloud_storage_skip_sync')
        if not skip:
            Folder = self.env['cloud.storage.folder'].sudo()
            for vals in vals_list:
                folder_id = vals.get('cloud_folder_id')
                if folder_id and not vals.get('res_model'):
                    # uploaded into a folder: attach the file to the folder's record
                    vals['res_model'], vals['res_id'] = Folder.browse(folder_id)._attachment_target()
            folders = self._cloud_folders_for(
                (v.get('res_model'), v.get('res_id')) for v in vals_list
                if not v.get('res_field') and not v.get('cloud_folder_id'))
            for vals in vals_list:
                if not vals.get('cloud_folder_id') and not vals.get('res_field'):
                    folder = folders.get((vals.get('res_model'), vals.get('res_id')))
                    if folder:
                        vals['cloud_folder_id'] = folder.id
        attachments = super().create(vals_list)
        if not skip:
            attachments._cloud_enqueue_upload()
        return attachments

    def write(self, vals):
        if self.env.context.get('cloud_storage_skip_sync'):
            return super().write(vals)
        moved = self.browse()
        old_paths = {}
        if 'cloud_folder_id' in vals:
            moved = self.filtered(lambda a: a.cloud_state == 'synced' and a.cloud_path)
            old_paths = {a.id: (a.cloud_path, a.cloud_folder_id.client_id) for a in moved}
        content_changed = {'raw', 'datas'} & set(vals)
        result = super().write(vals)
        Queue = self.env['cloud.storage.queue'].sudo()
        other_client = self.browse()
        for attachment in moved:
            folder = attachment.cloud_folder_id
            if not folder:
                continue
            old_path, old_client = old_paths[attachment.id]
            if folder.client_id != old_client:
                # another storage account: upload the file there (a move cannot cross accounts)
                if old_client and old_client.delete_remote_on_unlink:
                    Queue._enqueue('delete', old_client, path=old_path, priority=15)
                other_client |= attachment
                continue
            new_path = f"{folder.remote_path}/{attachment._cloud_file_name()}"
            if new_path != old_path:
                Queue._enqueue('move', folder.client_id, attachment=attachment,
                               path=old_path, new_path=new_path)
        to_upload = (self - moved) | other_client if 'cloud_folder_id' in vals else self.browse()
        if content_changed:
            to_upload |= self.filtered(lambda a: a.cloud_state in ('synced', 'error') and a.type == 'binary')
        to_upload._cloud_enqueue_upload()
        return result

    def unlink(self):
        if not self.env.context.get('cloud_storage_skip_sync'):
            Queue = self.env['cloud.storage.queue'].sudo()
            for attachment in self.sudo().filtered(lambda a: a.cloud_state == 'synced' and a.cloud_path):
                client = attachment.cloud_folder_id.client_id
                if client and client.delete_remote_on_unlink:
                    Queue._enqueue('delete', client, path=attachment.cloud_path, priority=15)
        return super().unlink()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _cloud_enqueue_upload(self):
        Queue = self.env['cloud.storage.queue'].sudo()
        for attachment in self.sudo():
            folder = attachment.cloud_folder_id
            if not folder or not folder.client_id or attachment.type != 'binary' or attachment.res_field:
                continue
            Queue._enqueue('upload', folder.client_id, attachment=attachment)
            attachment.with_context(cloud_storage_skip_sync=True).cloud_state = 'queued'

    def _cloud_file_name(self):
        """File name in the cloud, unique inside the folder."""
        self.ensure_one()
        name = sanitize(self.name or f'file-{self.id}')
        twins = self.sudo().search([
            ('cloud_folder_id', '=', self.cloud_folder_id.id), ('id', '<', self.id), ('name', '=', self.name),
        ], limit=1)
        if twins:
            stem, dot, ext = name.rpartition('.')
            name = f"{stem} ({self.id}).{ext}" if dot and stem else f"{name} ({self.id})"
        return name

    def action_open_in_cloud(self):
        self.ensure_one()
        client = self.cloud_folder_id.client_id
        url = self.url if self.type == 'url' else (
            client and self.cloud_path and client._provider().public_url(client._full_path(self.cloud_path)))
        if not url:
            return False
        return {'type': 'ir.actions.act_url', 'url': url, 'target': 'new'}

    def action_cloud_upload_now(self):
        self._cloud_enqueue_upload()
        clients = self.sudo().cloud_folder_id.client_id
        self.env['cloud.storage.queue']._process(clients=clients)
        return True
