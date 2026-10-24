from lxml import etree

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from ..models.access_rule_lines import mask_value
from .common import AccessCommon


@tagged('post_install', '-at_install')
class TestUiRestrictions(AccessCommon):

    def arch(self, user, view_type='form', model='res.partner'):
        return etree.fromstring(self.env[model].with_user(user).get_view(view_type=view_type)['arch'])

    def test_view_root_flags(self):
        self.make_rule(model_line_ids=[self.model_line(no_create=True, no_delete=True, no_duplicate=True,
                                                       no_import=True, no_export=True)])
        for view_type in ('form', 'list', 'kanban'):
            root = self.arch(self.alice, view_type)
            self.assertEqual(root.get('create'), '0', view_type)
            self.assertEqual(root.get('delete'), '0', view_type)
            self.assertEqual(root.get('import'), '0', view_type)
        self.assertEqual(self.arch(self.alice, 'list').get('export_xlsx'), '0')
        self.assertEqual(self.arch(self.alice).get('duplicate'), '0')
        self.assertIsNone(self.arch(self.bob).get('duplicate'))

    def test_fields(self):
        self.make_rule(field_line_ids=[
            self.field_line('phone', 'invisible'),
            self.field_line('city', 'readonly'),
            self.field_line('ref', 'required'),
            self.field_line('email', 'mask', mask_start=2, mask_end=4),
        ])
        root = self.arch(self.alice)
        self.assertTrue(all(n.get('invisible') == '1' for n in root.xpath("//field[@name='phone']")))
        self.assertTrue(all(n.get('readonly') == '1' for n in root.xpath("//field[@name='city']")))
        self.assertTrue(all(n.get('readonly') == '1' for n in root.xpath("//field[@name='email']")))
        self.assertTrue(all(n.get('required') == '1' for n in root.xpath("//field[@name='ref']")))
        list_root = self.arch(self.alice, 'list')
        self.assertTrue(all(n.get('column_invisible') == '1' for n in list_root.xpath("/list/field[@name='phone']")))
        self.assertNotIn('invisible', self.arch(self.bob).xpath("//field[@name='phone']")[0].attrib.get('invisible', ''))

        described = self.as_alice().fields_get(['city', 'email', 'phone', 'ref'], ['readonly', 'required', 'exportable'])
        self.assertTrue(described['city']['readonly'])
        self.assertTrue(described['ref']['required'])
        self.assertFalse(described['email']['exportable'])
        self.assertFalse(described['phone']['exportable'])

        rows = self.bristol.with_user(self.alice).web_read({'email': {}, 'phone': {}, 'email_normalized': {}})
        self.assertNotIn('contact@', rows[0]['email_normalized'], 'companion fields are masked too')
        masked = mask_value('contact@bristol.example.com', 2, 4)
        self.assertEqual(rows[0]['email'], masked)
        self.assertTrue(masked.startswith('co') and masked.endswith('.com') and '@' in masked and 'tact' not in masked)
        self.assertEqual(rows[0]['phone'], '+44 7700 900123', 'hidden is not masked')
        self.assertEqual(self.bristol.with_user(self.bob).web_read({'email': {}})[0]['email'],
                         'contact@bristol.example.com')
        with self.assertRaises(AccessError):
            self.bristol.with_user(self.alice).web_save({'city': 'Leeds'}, {})
        self.bristol.with_user(self.alice).web_save({'name': 'Bristol Limited'}, {})
        self.assertEqual(self.bristol.name, 'Bristol Limited')

        exported = self.bristol.with_user(self.alice).export_data(['name', 'email', 'phone'])['datas'][0]
        self.assertEqual(exported[1], masked)
        self.assertEqual(exported[2], '')

    def test_mask_domain_and_validation(self):
        self.make_rule(field_line_ids=[self.field_line('phone', 'mask', mask_start=3, mask_end=2,
                                                       domain="[('city', '=', 'Bristol')]")])
        rows = (self.bristol | self.bath).with_user(self.alice).web_read({'phone': {}})
        by_id = {row['id']: row['phone'] for row in rows}
        self.assertEqual(by_id[self.bristol.id], '+44 •••• ••••23')
        self.assertEqual(by_id[self.bath.id], '+44 7700 900456')
        with self.assertRaises(ValidationError):
            self.make_rule(name='bad', field_line_ids=[self.field_line('active', 'mask')])

    def test_buttons_and_pages(self):
        line = self.env['access.rule.element'].new({'model_id': self.partner_model.id, 'element_type': 'page'})
        self.assertIn('internal_notes', line.available)
        self.make_rule(element_line_ids=[
            (0, 0, {'model_id': self.partner_model.id, 'element_type': 'page', 'name': 'internal_notes'}),
            (0, 0, {'model_id': self.partner_model.id, 'element_type': 'button', 'name': 'action_archive'}),
        ])
        root = self.arch(self.alice)
        self.assertEqual(root.xpath("//page[@name='internal_notes']")[0].get('invisible'), '1')
        self.assertNotEqual(self.arch(self.bob).xpath("//page[@name='internal_notes']")[0].get('invisible'), '1')

    def test_chatter(self):
        rule = self.make_rule(model_line_ids=[self.model_line(hide_send_message=True, hide_followers=True)])
        root = self.arch(self.alice)
        marker = root.xpath("//div[contains(@class, 'o_am_chatter_marker')]")
        self.assertTrue(marker)
        self.assertIn('o_am_hide_send', marker[0].get('class'))
        self.assertIn('o_am_hide_followers', marker[0].get('class'))
        self.assertTrue(root.xpath('//chatter'))
        rule.model_line_ids.hide_chatter = True
        self.assertFalse(self.arch(self.alice).xpath('//chatter'))
        self.assertTrue(self.arch(self.bob).xpath('//chatter'))
        # activities cannot be scheduled on these records any more
        with self.assertRaises(AccessError):
            self.bristol.with_user(self.alice).activity_schedule('mail.mail_activity_data_todo', summary='Call')
        self.bristol.with_user(self.bob).activity_schedule('mail.mail_activity_data_todo', summary='Call')

    def test_toolbar(self):
        action = self.env['ir.actions.server'].create({
            'name': 'AM test action', 'model_id': self.partner_model.id, 'state': 'code', 'code': 'pass',
            'binding_model_id': self.partner_model.id})
        other = self.env['ir.actions.server'].create({
            'name': 'AM other action', 'model_id': self.partner_model.id, 'state': 'code', 'code': 'pass',
            'binding_model_id': self.partner_model.id})

        def toolbar(user):
            views = self.env['res.partner'].with_user(user).get_views([(False, 'list')], {'toolbar': True})
            return views['views']['list']['toolbar']

        rule = self.make_rule(model_line_ids=[self.model_line(action_ids=[(6, 0, action.ids)])])
        ids = [a['id'] for a in toolbar(self.alice).get('action', [])]
        self.assertNotIn(action.id, ids)
        self.assertIn(other.id, ids)
        self.assertIn(action.id, [a['id'] for a in toolbar(self.bob).get('action', [])])
        rule.model_line_ids.hide_all_actions = True
        self.assertNotIn('action', toolbar(self.alice))

    def test_search_view(self):
        self.make_rule(model_line_ids=[self.model_line(hide_filters=True, hide_group_by=True)])
        root = self.arch(self.alice, 'search')
        self.assertFalse(root.xpath('//filter'))
        self.assertTrue(self.arch(self.bob, 'search').xpath('//filter'))
        self.assertTrue(root.xpath('//field'), 'search fields stay')

    def test_archive_import_export(self):
        self.make_rule(model_line_ids=[self.model_line(no_archive=True, no_import=True, no_export=True)])
        with self.assertRaises(AccessError):
            self.bath.with_user(self.alice).action_archive()
        with self.assertRaises(AccessError):
            self.as_alice().load(['name'], [['Imported']])
        with self.assertRaises(AccessError):
            self.bath.with_user(self.alice).export_data(['name'])
        views = self.as_alice().get_views([(False, 'list'), (False, 'search')], {})
        self.assertTrue(views['models']['res.partner']['fields']['active']['readonly'])
        views = self.as_bob().get_views([(False, 'list'), (False, 'search')], {})
        self.assertFalse(views['models']['res.partner']['fields']['active'].get('readonly'))
        self.bath.with_user(self.bob).action_archive()
        self.as_bob().load(['name'], [['Imported by Bob']])

    def test_x2many_subviews(self):
        self.make_rule(model_line_ids=[self.model_line(no_create=True)],
                       field_line_ids=[self.field_line('phone', 'invisible')])
        root = self.arch(self.alice)
        # contacts (child_ids) of the partner form are partners too: their sub-view follows the same rules
        children = root.xpath("//field[@name='child_ids']")
        self.assertTrue(children)
        sub = [node for node in children[0] if node.tag in ('list', 'kanban', 'form')]
        self.assertTrue(sub and all(node.get('create') == '0' for node in sub))
