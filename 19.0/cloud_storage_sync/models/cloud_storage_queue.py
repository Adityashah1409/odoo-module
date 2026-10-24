import logging

from odoo import _, api, fields, models

from .providers import join_path

_logger = logging.getLogger(__name__)


class CloudStorageQueue(models.Model):
    """Pending storage operations, processed in batches by a cron (FIFO by priority)."""
    _name = 'cloud.storage.queue'
    _description = 'Cloud Storage Sync Task'
    _order = 'priority, id'

    client_id = fields.Many2one('cloud.storage.client', required=True, ondelete='cascade', index=True)
    operation = fields.Selection(
        [('mkdir', 'Create folder'), ('upload', 'Upload file'), ('move', 'Move / rename'),
         ('delete', 'Delete'), ('pull', 'Pull back to Odoo')],
        required=True)
    priority = fields.Integer(default=10, help="Lower runs first.")
    state = fields.Selection(
        [('todo', 'To do'), ('done', 'Done'), ('failed', 'Failed')],
        default='todo', required=True, index=True)
    folder_id = fields.Many2one('cloud.storage.folder', ondelete='cascade')
    attachment_id = fields.Many2one('ir.attachment', ondelete='cascade')
    path = fields.Char()
    new_path = fields.Char()
    attempts = fields.Integer(readonly=True)
    error = fields.Text(readonly=True)
    done_date = fields.Datetime(readonly=True)

    @api.model
    def _enqueue(self, operation, client, folder=None, attachment=None, path=None, new_path=None, priority=10):
        domain = [('state', '=', 'todo'), ('operation', '=', operation), ('client_id', '=', client.id),
                  ('folder_id', '=', folder.id if folder else False),
                  ('attachment_id', '=', attachment.id if attachment else False),
                  ('path', '=', path or False), ('new_path', '=', new_path or False)]
        task = self.search(domain, limit=1)
        if task:
            return task
        return self.create({
            'operation': operation, 'client_id': client.id, 'priority': priority,
            'folder_id': folder.id if folder else False,
            'attachment_id': attachment.id if attachment else False,
            'path': path, 'new_path': new_path,
        })

    def _max_attempts(self):
        return int(self.env['ir.config_parameter'].sudo().get_param('cloud_storage_sync.max_attempts', 5))

    @api.model
    def _process(self, clients=None, limit=500):
        domain = [('state', '=', 'todo'), ('client_id.state', '=', 'confirmed')]
        if clients:
            domain.append(('client_id', 'in', clients.ids))
        tasks = self.sudo().search(domain, limit=limit)
        max_attempts = self._max_attempts()
        for task in tasks:
            try:
                with self.env.cr.savepoint():
                    task._run()
                task.write({'state': 'done', 'done_date': fields.Datetime.now(), 'error': False})
            except Exception as e:  # noqa: BLE001 - a sync worker must never stop on one bad task
                attempts = task.attempts + 1
                task.write({
                    'attempts': attempts, 'error': str(e),
                    'state': 'failed' if attempts >= max_attempts else 'todo',
                })
                task.client_id._log(_("%(op)s failed (attempt %(n)s): %(error)s",
                                      op=dict(self._fields['operation'].selection)[task.operation],
                                      n=attempts, error=e),
                                    level='error', folder=task.folder_id, attachment=task.attachment_id)
                if task.folder_id and task.operation == 'mkdir':
                    task.folder_id.with_context(cloud_storage_skip_sync=True).sync_state = 'error'
                if task.attachment_id and task.operation == 'upload':
                    task.attachment_id.with_context(cloud_storage_skip_sync=True).cloud_state = 'error'
        return len(tasks)

    def _run(self):
        self.ensure_one()
        getattr(self, f'_run_{self.operation}')(self.client_id, self.client_id._provider())

    def _run_mkdir(self, client, provider):
        folder = self.folder_id
        if not folder or not folder.active:
            return
        provider.mkdir(client._full_path(folder.remote_path))
        folder.with_context(cloud_storage_skip_sync=True).sync_state = 'synced'

    def _run_upload(self, client, provider):
        attachment = self.attachment_id.sudo()
        folder = attachment.cloud_folder_id
        if not attachment or not folder or attachment.type != 'binary':
            return
        if folder.sync_state != 'synced':
            provider.mkdir(client._full_path(folder.remote_path))
            folder.with_context(cloud_storage_skip_sync=True).sync_state = 'synced'
        path = join_path(folder.remote_path, attachment._cloud_file_name())
        provider.upload(client._full_path(path), bytes(attachment.raw or b''))
        values = {'cloud_path': path, 'cloud_state': 'synced'}
        url = provider.public_url(client._full_path(path))
        if client.remove_local_binary and url:
            values.update({'type': 'url', 'url': url, 'raw': False,
                           'cloud_mimetype': attachment.mimetype})
        attachment.with_context(cloud_storage_skip_sync=True).write(values)

    def _run_move(self, client, provider):
        if not self.path or not self.new_path or self.path == self.new_path:
            return
        provider.move(client._full_path(self.path), client._full_path(self.new_path))
        # files keep their relative path below the moved item
        Attachment = self.env['ir.attachment'].sudo().with_context(cloud_storage_skip_sync=True)
        prefix = self.path + '/'
        # only this client's files: another storage account may use the same relative paths
        moved = Attachment.search([
            ('cloud_folder_id.client_id', '=', client.id),
            '|', ('cloud_path', '=', self.path), ('cloud_path', '=like', prefix + '%'),
        ])
        for attachment in moved:
            new_path = self.new_path + attachment.cloud_path[len(self.path):]
            values = {'cloud_path': new_path}
            if attachment.type == 'url':
                values['url'] = provider.public_url(client._full_path(new_path)) or attachment.url
            attachment.write(values)

    def _run_delete(self, client, provider):
        if self.path:
            provider.delete(client._full_path(self.path))

    def _run_pull(self, client, provider):
        attachment = self.attachment_id.sudo()
        if not attachment or not attachment.cloud_path:
            return
        data = provider.download(client._full_path(attachment.cloud_path))
        attachment.with_context(cloud_storage_skip_sync=True).write({
            'type': 'binary', 'url': False, 'raw': data,
            'mimetype': attachment.cloud_mimetype or attachment.mimetype,
            'cloud_state': 'local',
        })

    def action_requeue(self):
        self.write({'state': 'todo', 'attempts': 0, 'error': False})

    def action_run_now(self):
        self.env['cloud.storage.queue']._process(clients=self.client_id)
        return True

    @api.model
    def _cron_process(self):
        self._process()

    @api.autovacuum
    def _gc_done_tasks(self):
        self.search([('state', '=', 'done'),
                     ('done_date', '<', fields.Datetime.subtract(fields.Datetime.now(), days=7))]).unlink()
