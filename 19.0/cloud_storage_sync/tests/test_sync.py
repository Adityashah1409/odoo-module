import os

from odoo.tests import HttpCase, tagged

from .common import CloudStorageCase


@tagged('post_install', '-at_install')
class TestSync(CloudStorageCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Sync Partner', 'ref': 'CSSYNC'})
        cls.rule = cls.env['cloud.storage.rule'].create({
            'name': 'Partners', 'client_id': cls.client.id, 'model_id': cls.partner_model.id,
            'domain': "[('ref', '=', 'CSSYNC')]",
        })
        cls.rule._generate_folders()
        cls.folder = cls.Folder.search([('res_model', '=', 'res.partner'), ('res_id', '=', cls.partner.id)])

    def attach(self, name='quote.txt', data=b'hello'):
        return self.Attachment.create({'name': name, 'raw': data,
                                       'res_model': 'res.partner', 'res_id': self.partner.id})

    def test_attachment_gets_folder_and_uploads(self):
        attachment = self.attach()
        self.assertEqual(attachment.cloud_folder_id, self.folder)
        self.assertEqual(attachment.cloud_state, 'queued')
        self.run_queue()
        self.assertEqual(attachment.cloud_state, 'synced')
        self.assertEqual(attachment.cloud_path, 'Partners/Sync Partner/quote.txt')
        with open(self.remote('Partners', 'Sync Partner', 'quote.txt'), 'rb') as f:
            self.assertEqual(f.read(), b'hello')

    def test_same_name_files_do_not_overwrite(self):
        first, second = self.attach(data=b'one'), self.attach(data=b'two')
        self.run_queue()
        self.assertNotEqual(first.cloud_path, second.cloud_path)
        self.assertTrue(second.cloud_path.endswith(f'quote ({second.id}).txt'))

    def test_field_binaries_are_ignored(self):
        attachment = self.Attachment.create({'name': 'image_1920', 'raw': b'x', 'res_model': 'res.partner',
                                             'res_id': self.partner.id, 'res_field': 'image_1920'})
        self.assertFalse(attachment.cloud_folder_id)

    def test_content_change_reuploads(self):
        attachment = self.attach()
        self.run_queue()
        attachment.raw = b'updated'
        self.assertEqual(attachment.cloud_state, 'queued')
        self.run_queue()
        with open(self.remote('Partners', 'Sync Partner', 'quote.txt'), 'rb') as f:
            self.assertEqual(f.read(), b'updated')

    def test_cloud_only_and_pull_back(self):
        self.client.remove_local_binary = True
        attachment = self.attach(data=b'big file')
        self.run_queue()
        self.assertEqual(attachment.type, 'url')
        self.assertEqual(attachment.url, 'https://files.example.com/Odoo/Partners/Sync%20Partner/quote.txt')
        self.client.action_pull_back()
        self.run_queue()
        self.assertEqual(attachment.type, 'binary')
        self.assertEqual(bytes(attachment.raw), b'big file')
        self.assertEqual(attachment.cloud_state, 'local')

    def test_unlink_deletes_remote_file(self):
        attachment = self.attach()
        self.run_queue()
        path = self.remote('Partners', 'Sync Partner', 'quote.txt')
        self.assertTrue(os.path.exists(path))
        attachment.unlink()
        self.run_queue()
        self.assertFalse(os.path.exists(path))

    def test_manual_folder_upload_and_move(self):
        manual = self.Folder.create({'name': 'Board', 'client_id': self.client.id})
        attachment = self.Attachment.create({'name': 'minutes.txt', 'raw': b'm', 'cloud_folder_id': manual.id})
        self.assertEqual((attachment.res_model, attachment.res_id), ('cloud.storage.folder', manual.id))
        self.run_queue()
        self.assertTrue(os.path.exists(self.remote('Board', 'minutes.txt')))
        manual.name = 'Board 2026'
        self.run_queue()
        self.assertTrue(os.path.exists(self.remote('Board 2026', 'minutes.txt')))
        self.assertEqual(attachment.cloud_path, 'Board 2026/minutes.txt')

    def test_backward_sync(self):
        self.run_queue()
        os.makedirs(self.remote('Partners', 'Sync Partner', 'Scans'))
        with open(self.remote('Partners', 'Sync Partner', 'from-cloud.txt'), 'wb') as f:
            f.write(b'added in the cloud')
        self.client._backward_sync()
        imported = self.Attachment.search([('cloud_folder_id', '=', self.folder.id), ('name', '=', 'from-cloud.txt')])
        self.assertEqual(bytes(imported.raw), b'added in the cloud')
        self.assertEqual((imported.res_model, imported.res_id), ('res.partner', self.partner.id))
        self.assertEqual(imported.cloud_state, 'synced')
        self.assertIn('Scans', self.folder.child_ids.mapped('name'))
        # vanished files are flagged, not deleted
        os.remove(self.remote('Partners', 'Sync Partner', 'from-cloud.txt'))
        self.client._backward_sync()
        self.assertEqual(imported.cloud_state, 'missing')

    def test_paused_client_and_retries(self):
        self.client.action_pause()
        attachment = self.attach()
        self.assertEqual(self.run_queue(), 0, "paused clients are skipped")
        self.client.action_resume()
        self.client.local_path = '/proc/forbidden_path_for_test'
        self.env['ir.config_parameter'].set_param('cloud_storage_sync.max_attempts', 2)
        self.run_queue()
        task = self.Queue.search([('attachment_id', '=', attachment.id)])
        self.assertEqual((task.state, task.attempts), ('todo', 1))
        self.run_queue()
        self.assertEqual((task.state, task.attempts), ('failed', 2))
        self.assertEqual(attachment.cloud_state, 'error')
        self.assertTrue(self.env['cloud.storage.log'].search_count(
            [('client_id', '=', self.client.id), ('level', '=', 'error')]))
        self.client.local_path = self.tmp
        task.action_requeue()
        self.run_queue()
        self.assertEqual(attachment.cloud_state, 'synced')


@tagged('post_install', '-at_install')
class TestZipDownload(HttpCase, CloudStorageCase):

    def test_zip_download(self):
        partner = self.env['res.partner'].create({'name': 'Zip Partner'})
        folder = self.Folder.create({'name': 'Zip', 'client_id': self.client.id})
        self.Attachment.create({'name': 'a.txt', 'raw': b'zip me', 'cloud_folder_id': folder.id})
        self.Attachment.create({'name': 'b.txt', 'raw': b'other', 'res_model': 'res.partner', 'res_id': partner.id})
        self.run_queue()
        self.authenticate('admin', 'admin')
        response = self.url_open(f'/cloud_storage_sync/folder/{folder.id}/zip')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], 'application/zip')
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(archive.namelist(), ['Zip/a.txt'])
            self.assertEqual(archive.read('Zip/a.txt'), b'zip me')
