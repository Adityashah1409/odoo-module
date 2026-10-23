import os
import shutil
import tempfile

from odoo.tests import TransactionCase


class CloudStorageCase(TransactionCase):
    """A connected 'local folder' client pointing to a temporary directory."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.mkdtemp(prefix='cloud_storage_test_')
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.client = cls.env['cloud.storage.client'].create({
            'name': 'Test storage',
            'provider': 'local',
            'local_path': cls.tmp,
            'root_folder': 'Odoo',
            'browser_base_url': 'https://files.example.com',
        })
        cls.client.action_test_connection()
        cls.Queue = cls.env['cloud.storage.queue']
        cls.Folder = cls.env['cloud.storage.folder']
        cls.Attachment = cls.env['ir.attachment']
        cls.partner_model = cls.env['ir.model']._get('res.partner')

    def remote(self, *parts):
        return os.path.join(self.tmp, 'Odoo', *parts)

    def run_queue(self):
        return self.Queue._process(clients=self.client)
