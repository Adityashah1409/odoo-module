import os

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import CloudStorageCase


@tagged('post_install', '-at_install')
class TestFolderRules(CloudStorageCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env['res.partner'].create({'name': 'Alpha Corp', 'ref': 'CSTEST'})
        cls.company_b = cls.env['res.partner'].create({'name': 'Beta/Inc', 'ref': 'CSTEST'})
        cls.contact = cls.env['res.partner'].create({'name': 'Ann Alpha', 'parent_id': cls.company_a.id,
                                                     'ref': 'CSTEST-C'})
        cls.rule = cls.env['cloud.storage.rule'].create({
            'name': 'Customers',
            'client_id': cls.client.id,
            'model_id': cls.partner_model.id,
            'domain': "[('ref', '=', 'CSTEST')]",
            'subfolder_names': 'Contracts, Photos',
        })

    def test_generate_creates_record_folders(self):
        self.rule._generate_folders()
        folders = self.rule.folder_ids.filtered('res_model')
        self.assertEqual(set(folders.mapped('res_id')), {self.company_a.id, self.company_b.id})
        folder_b = folders.filtered(lambda f: f.res_id == self.company_b.id)
        self.assertEqual(folder_b.remote_path, 'Customers/Beta-Inc', "slashes are sanitized")
        self.assertEqual(sorted(folder_b.child_ids.mapped('name')), ['Contracts', 'Photos'])

    def test_generate_is_idempotent_and_syncs(self):
        self.rule._generate_folders()
        count = self.Folder.search_count([('rule_id', '=', self.rule.id)])
        self.rule._generate_folders()
        self.assertEqual(self.Folder.search_count([('rule_id', '=', self.rule.id)]), count)
        self.run_queue()
        self.assertTrue(os.path.isdir(self.remote('Customers', 'Alpha Corp', 'Contracts')))
        self.assertTrue(all(f.sync_state == 'synced' for f in self.rule.folder_ids))

    def test_rename_record_moves_folder(self):
        self.rule._generate_folders()
        self.run_queue()
        self.company_a.name = 'Alpha Group'
        self.rule._generate_folders()
        self.run_queue()
        self.assertTrue(os.path.isdir(self.remote('Customers', 'Alpha Group', 'Photos')))
        self.assertFalse(os.path.exists(self.remote('Customers', 'Alpha Corp')))

    def test_child_rule(self):
        child = self.env['cloud.storage.rule'].create({
            'name': 'Contacts',
            'parent_id': self.rule.id,
            'model_id': self.partner_model.id,
            'parent_field_id': self.env['ir.model.fields']._get('res.partner', 'parent_id').id,
            'domain': "[('ref', '=', 'CSTEST-C')]",
            'name_expression': 'record.name',
        })
        self.assertEqual(child.client_id, self.client, "client is inherited from the parent rule")
        (self.rule | child)._generate_folders()
        contact_folder = self.Folder.search([('res_model', '=', 'res.partner'), ('res_id', '=', self.contact.id)])
        self.assertEqual(contact_folder.remote_path, 'Customers/Alpha Corp/Contacts/Ann Alpha')

    def test_record_leaving_domain_is_retired(self):
        self.rule._generate_folders()
        self.run_queue()
        self.company_b.ref = 'OTHER'
        self.rule._generate_folders()
        folder_b = self.Folder.with_context(active_test=False).search(
            [('res_model', '=', 'res.partner'), ('res_id', '=', self.company_b.id)])
        self.assertFalse(folder_b.active)
        self.run_queue()
        self.assertFalse(os.path.exists(self.remote('Customers', 'Beta-Inc')))

    def test_max_folders(self):
        self.rule.max_folders = 1
        self.rule._generate_folders()
        self.assertEqual(len(self.rule.folder_ids.filtered('res_model')), 1)

    def test_invalid_rule(self):
        with self.assertRaises(ValidationError):
            self.env['cloud.storage.rule'].create({
                'name': 'Broken', 'client_id': self.client.id, 'model_id': self.partner_model.id,
                'domain': "[('no_such_field', '=', 1)]",
            })
        with self.assertRaises(ValidationError):
            self.env['cloud.storage.rule'].create({
                'name': 'No link', 'parent_id': self.rule.id, 'model_id': self.partner_model.id,
            })
