from datetime import timedelta

from odoo import fields
from odoo.tests import Form, tagged

from .common import HubspotCommon


@tagged('post_install', '-at_install')
class TestExport(HubspotCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env['res.partner'].create({
            'name': 'Wayne Enterprises', 'is_company': True, 'website': 'https://www.wayne.example.com',
            'phone': '+1 555 0100', 'city': 'Gotham', 'user_id': cls.env.ref('base.user_admin').id})
        cls.contact = cls.env['res.partner'].create({
            'name': 'Lucius Fox', 'email': 'lucius@wayne.example.com', 'function': 'CEO', 'parent_id': cls.company.id})

    def test_partners(self):
        self.enable('companies', 'contacts', direction='export')
        self.account.action_export_now()
        company_link, contact_link = self.link('companies', self.company), self.link('contacts', self.contact)
        hs_company = self.fake.get('companies', company_link.hubspot_id)
        self.assertEqual(hs_company['properties']['name'], 'Wayne Enterprises')
        self.assertEqual(hs_company['properties']['domain'], 'wayne.example.com')
        self.assertEqual(hs_company['properties']['hubspot_owner_id'], '501')
        hs_contact = self.fake.get('contacts', contact_link.hubspot_id)
        self.assertEqual((hs_contact['properties']['firstname'], hs_contact['properties']['lastname'],
                          hs_contact['properties']['jobtitle']), ('Lucius', 'Fox', 'CEO'))
        self.assertEqual(self.fake.linked('contacts', contact_link.hubspot_id, 'companies'), [company_link.hubspot_id])
        self.assertNotIn(self.admin.partner_id, self.env['res.partner'].search([('hubspot_id', '!=', False)]),
                         'internal users are not exported')
        # unchanged records are skipped, changes are sent with PATCH
        calls = len(self.fake.calls)
        self.obj('contacts').last_export = False
        self.account.action_export_now()
        self.assertFalse([c for c in self.fake.calls[calls:] if c[0] in ('PATCH', 'POST') and 'objects/contacts' in c[1]
                          and not c[1].endswith('search')])
        self.contact.phone = '+1 555 0199'
        self.account.action_export_now()
        self.assertEqual(self.fake.get('contacts', contact_link.hubspot_id)['properties']['phone'], '+1 555 0199')
        self.assertEqual(self.jobs(res_id=self.contact.id, direction='export', state='done')[-1:].result, 'updated')

    def test_existing_contact_is_not_duplicated(self):
        existing = self.fake.add('contacts', {'email': 'lucius@wayne.example.com', 'firstname': 'L.'})
        self.enable('contacts', direction='export')
        self.account.action_export_now()
        self.assertEqual(self.link('contacts', self.contact).hubspot_id, existing)
        self.assertEqual(len(self.fake.all('contacts')), 1)
        self.assertEqual(self.fake.get('contacts', existing)['properties']['firstname'], 'Lucius')

    def test_deleted_in_hubspot_is_recreated(self):
        self.enable('companies', direction='export')
        self.account.action_export_now()
        old_id = self.link('companies', self.company).hubspot_id
        self.fake.get('companies', old_id)['archived'] = True
        self.company.phone = '+1 555 0111'
        self.account.action_export_now()
        new_link = self.link('companies', self.company)
        self.assertNotEqual(new_link.hubspot_id, old_id)
        self.assertEqual(len(self.fake.all('companies')), 1)

    def test_deals(self):
        self.enable('companies', 'contacts', 'deals', direction='export')
        lead = self.env['crm.lead'].create({'name': 'Batmobile fleet', 'type': 'opportunity', 'partner_id': self.contact.id,
                                            'expected_revenue': 50000, 'date_deadline': fields.Date.today() + timedelta(days=20),
                                            'stage_id': self.first_stage.id, 'user_id': self.admin.id})
        self.account.stage_ids.filtered(lambda s: not s.is_closed).crm_stage_id = False
        self.account.stage_ids.filtered(lambda s: s.hubspot_id == 'qualifiedtobuy').crm_stage_id = self.first_stage
        self.account.action_export_now()
        deal = self.fake.get('deals', self.link('deals', lead).hubspot_id)
        self.assertEqual((deal['properties']['dealname'], deal['properties']['dealstage'], deal['properties']['amount']),
                         ('Batmobile fleet', 'qualifiedtobuy', '50000.0'))
        self.assertEqual(self.fake.linked('deals', deal['id'], 'contacts'), [self.link('contacts', self.contact).hubspot_id])
        self.assertEqual(self.fake.linked('deals', deal['id'], 'companies'), [self.link('companies', self.company).hubspot_id])
        lead.action_set_won()
        self.account.action_export_now()
        self.assertEqual(self.fake.get('deals', deal['id'])['properties']['dealstage'], 'closedwon')
        other = self.env['crm.lead'].create({'name': 'Lost one', 'type': 'opportunity'})
        other.action_set_lost()
        self.account.action_export_now()
        self.assertEqual(self.fake.get('deals', self.link('deals', other).hubspot_id)['properties']['dealstage'], 'closedlost')

    def test_quotes_and_invoices(self):
        self.enable('companies', 'products', 'quotes', 'invoices', direction='export')
        product = self.env['product.product'].create({'name': 'Grappling hook', 'list_price': 250, 'default_code': 'GH-1'})
        order = self.env['sale.order'].create({'partner_id': self.company.id, 'order_line': [
            (0, 0, {'product_id': product.id, 'product_uom_qty': 4, 'price_unit': 240, 'discount': 5})]})
        self.account.action_export_now()
        quote = self.fake.get('quotes', self.link('quotes', order).hubspot_id)
        self.assertEqual(quote['properties']['hs_title'], order.name)
        self.assertEqual(quote['properties']['hs_status'], 'DRAFT')
        self.assertNotIn('_lines', quote['properties'], 'technical keys are not sent')
        items = self.fake.linked('quotes', quote['id'], 'line_items')
        self.assertEqual(len(items), 1)
        item = self.fake.get('line_items', items[0])['properties']
        self.assertEqual((item['quantity'], item['price'], item['hs_discount_percentage']), ('4.0', '240.0', '5.0'))
        self.assertEqual(item['hs_product_id'], self.link('products', product.product_tmpl_id).hubspot_id)
        self.assertEqual(self.fake.linked('quotes', quote['id'], 'companies'), [self.link('companies', self.company).hubspot_id])
        # changing a line replaces the line items
        order.order_line.product_uom_qty = 6
        self.account.action_export_now()
        new_items = self.fake.linked('quotes', quote['id'], 'line_items')
        self.assertEqual(len([i for i in new_items if not self.fake.get('line_items', i)['archived']]), 1)
        self.assertTrue(self.fake.get('line_items', items[0])['archived'])
        # invoice
        invoice = self.env['account.move'].create({'move_type': 'out_invoice', 'partner_id': self.company.id,
                                                   'invoice_date': fields.Date.today(),
                                                   'invoice_line_ids': [(0, 0, {'product_id': product.id, 'quantity': 2,
                                                                                'price_unit': 250})]})
        invoice.action_post()
        self.account.action_export_now()
        hs_invoice = self.fake.get('invoices', self.link('invoices', invoice).hubspot_id)
        self.assertEqual(hs_invoice['properties']['hs_invoice_status'], 'open')
        self.assertEqual(len(self.fake.linked('invoices', hs_invoice['id'], 'line_items')), 1)

    def test_engagements(self):
        self.enable('companies', 'contacts', 'notes', 'tasks', 'meetings', 'emails', direction='export')
        self.contact.message_post(body='Discussed the <b>contract</b>.', message_type='comment', subtype_xmlid='mail.mt_note')
        activity = self.contact.activity_schedule('mail.mail_activity_data_todo', summary='Call back',
                                                  date_deadline=fields.Date.today() + timedelta(days=2), user_id=self.admin.id)
        event = self.env['calendar.event'].with_context(no_mail_to_attendees=True).create({
            'name': 'Board meeting', 'start': fields.Datetime.now(), 'stop': fields.Datetime.now() + timedelta(hours=1),
            'partner_ids': [(6, 0, (self.contact | self.admin.partner_id).ids)], 'user_id': self.admin.id})
        unrelated = self.env['res.partner'].create({'name': 'No email person'})
        unrelated.message_post(body='Not synchronized', message_type='comment', subtype_xmlid='mail.mt_note')
        self.account.action_export_now()   # partners first, then engagements of synchronized partners
        self.account.action_export_now()
        contact_id = self.link('contacts', self.contact).hubspot_id
        notes = self.fake.all('notes')
        self.assertEqual(len(notes), 1, [n['properties'].get('hs_note_body') for n in notes])
        self.assertIn('contract', notes[0]['properties']['hs_note_body'])
        self.assertEqual(self.fake.linked('notes', notes[0]['id'], 'contacts'), [contact_id])
        task = self.fake.get('tasks', self.link('tasks', activity).hubspot_id)
        self.assertEqual((task['properties']['hs_task_subject'], task['properties']['hs_task_status']), ('Call back', 'NOT_STARTED'))
        meeting = self.fake.get('meetings', self.link('meetings', event).hubspot_id)
        self.assertEqual(meeting['properties']['hs_meeting_title'], 'Board meeting')
        self.assertEqual(self.fake.linked('meetings', meeting['id'], 'contacts'), [contact_id])
        activity.action_feedback(feedback='Done')
        self.account.action_export_now()
        self.assertEqual(self.fake.get('tasks', task['id'])['properties']['hs_task_status'], 'COMPLETED')

    def test_export_wizard(self):
        wizard = Form(self.env['hubspot.export.wizard'].with_context(
            active_model='res.partner', active_ids=(self.company | self.contact).ids))
        self.assertEqual(wizard.account_id, self.account)
        self.assertEqual(wizard.record_count, 2)
        action = wizard.save().action_export()
        self.assertEqual(action['params']['type'], 'success')
        self.assertTrue(self.link('companies', self.company))
        self.assertTrue(self.link('contacts', self.contact))

    def test_mapping_export(self):
        mapping_field = self.env['ir.model.fields']._get('res.partner', 'ref')
        self.env['hubspot.field.mapping'].create({'account_id': self.account.id, 'object_type': 'contacts',
                                                  'field_id': mapping_field.id, 'hubspot_property': 'customer_reference',
                                                  'direction': 'export'})
        self.contact.ref = 'C-001'
        self.enable('contacts', direction='export')
        self.account.action_export_now()
        hs = self.fake.get('contacts', self.link('contacts', self.contact).hubspot_id)
        self.assertEqual(hs['properties']['customer_reference'], 'C-001')

    def test_round_trip_does_not_ping_pong(self):
        """An imported record is not exported back unless it changes in Odoo."""
        company = self.fake.add('companies', {'name': 'Stark Industries', 'domain': 'stark.example.com'})
        self.account.object_ids.filtered(lambda o: o.object_type == 'companies').write(
            {'import_enabled': True, 'export_enabled': True})
        self.account.action_sync_now()
        calls = [c for c in self.fake.calls if c[0] == 'PATCH']
        self.assertFalse(calls, 'nothing sent back')
        self.assertEqual(self.record('companies', company).name, 'Stark Industries')
