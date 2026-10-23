from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .providers import PROVIDERS, StorageError, join_path


class CloudStorageClient(models.Model):
    _name = 'cloud.storage.client'
    _description = 'Cloud Storage Client'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    provider = fields.Selection(
        [('webdav', 'WebDAV (Nextcloud, ownCloud, Synology, QNAP, TrueNAS)'),
         ('local', 'Server folder (local disk or mounted NAS)')],
        required=True, default='webdav')
    state = fields.Selection(
        [('draft', 'Not connected'), ('confirmed', 'Connected'),
         ('paused', 'Paused'), ('error', 'Error')],
        default='draft', required=True, readonly=True, copy=False)
    root_folder = fields.Char(
        default='Odoo', required=True,
        help="Folder inside the storage where Odoo keeps its tree.")

    # WebDAV
    webdav_url = fields.Char(
        string="WebDAV URL", groups='cloud_storage_sync.group_cloud_storage_manager',
        help="e.g. https://cloud.example.com/remote.php/dav/files/odoo")
    webdav_user = fields.Char(groups='cloud_storage_sync.group_cloud_storage_manager')
    webdav_password = fields.Char(groups='cloud_storage_sync.group_cloud_storage_manager')
    verify_ssl = fields.Boolean(default=True, groups='cloud_storage_sync.group_cloud_storage_manager')
    # Local folder
    local_path = fields.Char(
        groups='cloud_storage_sync.group_cloud_storage_manager',
        help="Absolute path on the Odoo server, e.g. /mnt/nas/odoo")

    browser_base_url = fields.Char(
        string="Browser base URL",
        help="Public or internal URL matching the storage root, used to open "
             "files in the browser and for link attachments.")
    backward_sync = fields.Boolean(
        default=True,
        help="Mirror files and folders added directly in the storage back into Odoo.")
    remove_local_binary = fields.Boolean(
        string="Keep files only in the cloud",
        help="After upload, replace the Odoo copy by a link to the cloud file "
             "(needs a browser base URL). Saves filestore space.")
    delete_remote_on_unlink = fields.Boolean(
        string="Delete in cloud when deleted in Odoo", default=True)
    last_sync = fields.Datetime(readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)

    folder_ids = fields.One2many('cloud.storage.folder', 'client_id')
    folder_count = fields.Integer(compute='_compute_counts')
    queue_count = fields.Integer(compute='_compute_counts')
    log_count = fields.Integer(compute='_compute_counts')

    def _compute_counts(self):
        folders = dict(self.env['cloud.storage.folder']._read_group(
            [('client_id', 'in', self.ids)], ['client_id'], ['__count']))
        queue = dict(self.env['cloud.storage.queue'].sudo()._read_group(
            [('client_id', 'in', self.ids), ('state', '!=', 'done')], ['client_id'], ['__count']))
        logs = dict(self.env['cloud.storage.log'].sudo()._read_group(
            [('client_id', 'in', self.ids)], ['client_id'], ['__count']))
        for client in self:
            client.folder_count = folders.get(client, 0)
            client.queue_count = queue.get(client, 0)
            client.log_count = logs.get(client, 0)

    # ------------------------------------------------------------------
    # Provider access
    # ------------------------------------------------------------------
    def _provider(self):
        self.ensure_one()
        return PROVIDERS[self.provider](self.sudo())

    def _full_path(self, path):
        """Path relative to the storage, including the client root folder."""
        self.ensure_one()
        return join_path(self.root_folder, path)

    def _log(self, message, level='info', folder=False, attachment=False):
        self.env['cloud.storage.log'].sudo().create({
            'client_id': self.id,
            'level': level,
            'message': message,
            'folder_id': folder.id if folder else False,
            'attachment_id': attachment.id if attachment else False,
        })

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_test_connection(self):
        for client in self:
            try:
                provider = client._provider()
                provider.test()
                provider.mkdir(client.root_folder)
            except StorageError as e:
                client.write({'state': 'error', 'last_error': str(e)})
                client._log(_("Connection failed: %s", e), level='error')
                raise UserError(_("Connection to %(name)s failed:\n%(error)s", name=client.name, error=e))
            client.write({'state': 'confirmed', 'last_error': False})
            client._log(_("Connection confirmed."))
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': _("Connection successful."),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }

    def action_pause(self):
        self.filtered(lambda c: c.state == 'confirmed').write({'state': 'paused'})

    def action_resume(self):
        self.filtered(lambda c: c.state == 'paused').write({'state': 'confirmed'})

    def action_sync_now(self):
        """Run the whole cycle for these clients: rules, queue, backward sync."""
        self.env['cloud.storage.rule'].search([('client_id', 'in', self.ids)])._generate_folders()
        self.env['cloud.storage.queue']._process(clients=self)
        for client in self.filtered('backward_sync'):
            client._backward_sync()
        self.write({'last_sync': fields.Datetime.now()})
        return True

    def action_pull_back(self):
        """Reverse sync: bring every cloud-only file back into the Odoo filestore."""
        Queue = self.env['cloud.storage.queue'].sudo()
        for client in self:
            attachments = self.env['ir.attachment'].sudo().search([
                ('cloud_folder_id.client_id', '=', client.id),
                ('cloud_state', '=', 'synced'), ('type', '=', 'url'),
            ])
            for attachment in attachments:
                Queue._enqueue('pull', client, attachment=attachment, priority=1)
        return True

    def action_view_folders(self):
        return self._open('cloud_storage_sync.action_cloud_storage_folder')

    def action_view_queue(self):
        return self._open('cloud_storage_sync.action_cloud_storage_queue')

    def action_view_logs(self):
        return self._open('cloud_storage_sync.action_cloud_storage_log')

    def _open(self, xmlid):
        action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
        action['domain'] = [('client_id', '=', self.id)]
        action['context'] = {'default_client_id': self.id}
        return action

    # ------------------------------------------------------------------
    # Backward sync (storage -> Odoo)
    # ------------------------------------------------------------------
    def _backward_sync(self, limit=200):
        """Mirror items created directly in the storage.

        New files become attachments of the folder's record, new sub-folders
        become manual folders, and synced files that vanished are flagged.
        """
        self.ensure_one()
        if self.state != 'confirmed':
            return
        Attachment = self.env['ir.attachment'].sudo()
        Folder = self.env['cloud.storage.folder'].sudo()
        provider = self._provider()
        folders = Folder.search([('client_id', '=', self.id), ('sync_state', '=', 'synced')],
                                order='last_backward_check asc, id', limit=limit)
        for folder in folders:
            try:
                items = provider.listdir(self._full_path(folder.remote_path))
            except StorageError as e:
                self._log(_("Backward sync failed: %s", e), level='error', folder=folder)
                continue
            remote_files = {i['name']: i for i in items if not i['is_dir']}
            remote_dirs = {i['name'] for i in items if i['is_dir']}
            known = Attachment.search([('cloud_folder_id', '=', folder.id)])
            known_names = {a.cloud_path.rsplit('/', 1)[-1] for a in known if a.cloud_path}
            # new files
            for name in sorted(set(remote_files) - known_names):
                path = join_path(folder.remote_path, name)
                try:
                    data = provider.download(self._full_path(path))
                except StorageError as e:
                    self._log(_("Could not download %(path)s: %(error)s", path=path, error=e), level='error')
                    continue
                res_model, res_id = folder._attachment_target()
                attachment = Attachment.with_context(cloud_storage_skip_sync=True).create({
                    'name': name, 'raw': data,
                    'res_model': res_model, 'res_id': res_id,
                    'cloud_folder_id': folder.id,
                    'cloud_path': path, 'cloud_state': 'synced',
                })
                self._log(_("Imported %s from the storage.", path), folder=folder, attachment=attachment)
            # vanished files
            for attachment in known.filtered(lambda a: a.cloud_state == 'synced' and a.cloud_path):
                if attachment.cloud_path.rsplit('/', 1)[-1] not in remote_files:
                    attachment.with_context(cloud_storage_skip_sync=True).cloud_state = 'missing'
                    self._log(_("%s is missing in the storage.", attachment.cloud_path),
                              level='warning', attachment=attachment)
            # new folders
            child_names = {child.sanitized_name for child in folder.child_ids}
            for name in sorted(remote_dirs - child_names):
                Folder.with_context(cloud_storage_skip_sync=True).create({
                    'name': name, 'parent_id': folder.id, 'client_id': self.id,
                    'manual': True, 'sync_state': 'synced',
                })
            folder.last_backward_check = fields.Datetime.now()

    # ------------------------------------------------------------------
    # Crons
    # ------------------------------------------------------------------
    @api.model
    def _cron_backward_sync(self):
        for client in self.search([('state', '=', 'confirmed'), ('backward_sync', '=', True)]):
            client._backward_sync()
            client.last_sync = fields.Datetime.now()
