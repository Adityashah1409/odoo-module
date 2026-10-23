from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import CloudStorageCase


@tagged('post_install', '-at_install')
class TestAccess(CloudStorageCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.file_user = new_test_user(cls.env, 'cs_file_user', groups='cloud_storage_sync.group_cloud_storage_user')
        cls.other_user = new_test_user(cls.env, 'cs_other_user', groups='cloud_storage_sync.group_cloud_storage_user')
        cls.employee = new_test_user(cls.env, 'cs_employee', groups='base.group_user')
        cls.open_folder = cls.Folder.create({'name': 'Shared', 'client_id': cls.client.id})
        cls.private_folder = cls.Folder.create({'name': 'HR only', 'client_id': cls.client.id,
                                                'user_ids': [(4, cls.file_user.id)]})

    def test_folder_restrictions(self):
        visible = self.Folder.with_user(self.file_user).search([('client_id', '=', self.client.id)])
        self.assertIn(self.private_folder, visible)
        visible = self.Folder.with_user(self.other_user).search([('client_id', '=', self.client.id)])
        self.assertIn(self.open_folder, visible)
        self.assertNotIn(self.private_folder, visible)

    def test_file_user_cannot_configure(self):
        with self.assertRaises(AccessError):
            self.env['cloud.storage.client'].with_user(self.file_user).create({'name': 'x', 'provider': 'local'})
        with self.assertRaises(AccessError):
            self.client.with_user(self.file_user).read(['webdav_password'])

    def test_file_user_uploads_into_folder(self):
        attachment = self.Attachment.with_user(self.file_user).create({
            'name': 'note.txt', 'raw': b'n', 'cloud_folder_id': self.open_folder.id})
        self.assertEqual(attachment.cloud_state, 'queued')
        self.run_queue()
        self.assertEqual(attachment.cloud_state, 'synced')

    def test_employee_cannot_open_file_manager(self):
        with self.assertRaises(AccessError):
            self.Folder.with_user(self.employee).create({'name': 'Nope', 'client_id': self.client.id})
