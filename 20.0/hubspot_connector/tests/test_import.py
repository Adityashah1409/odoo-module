from markupsafe import Markup

from odoo.tests import tagged

from .common import HubspotCommon


@tagged('post_install', '-at_install')
class TestImport(HubspotCommon):

    def _crm(self):
        f = self.fake
        self.acme = f.add('companies', {'name': 'Acme Corp', 'domain': 'acme.example.com', 'phone': '+32 2 555 00 00',
                                        'city': 'Brussels', 'country': 'Belgium', 'hubspot_owner_id': '501'})
        self.jane = f.add('contacts', {'firstname': 'Jane', 'lastname': 'Doe', 'email': 'jane@acme.example.com',
                                       'jobtitle': 'CTO', 'phone': '+32 470 00 00 01'}, [('companies', self.acme)])
        self.bob = f.add('contacts', {'firstname': 'Bob', 'lastname': 'Solo', 'email': 'bob@solo.example.com',
                                      'mobilephone': '+32 470 99 99 99'})
        self.deal = f.add('deals', {'dealname': 'Acme renewal', 'amount': '12000', 'closedate': '2026-04-30T00:00:00Z',
                                    'dealstage': 'qualifiedtobuy', 'pipeline': 'default', 'hubspot_owner_id': '501'},
                          [('companies', self.acme), ('contacts', self.jane)])

    def test_companies_contacts_deals(self):
        self._crm()
        existing = self.env['res.partner'].create({'name': 'Bob (old)', 'email': 'BOB@solo.example.com'})
        self.enable('companies', 'contacts', 'deals')
        self.account.action_import_now()
        company = self.record('companies', self.acme)
        self.assertEqual((company.name, company.city, company.country_id.code, company.user_id),
                         ('Acme Corp', 'Brussels', 'BE', self.admin))
        self.assertFalse(company.parent_id)
        self.assertIn('acme.example.com', company.website)
        jane = self.record('contacts', self.jane)
        self.assertEqual((jane.name, jane.email, jane.function, jane.parent_id), ('Jane Doe', 'jane@acme.example.com', 'CTO', company))
        bob = self.record('contacts', self.bob)
        self.assertEqual(bob, existing, 'matched by e-mail instead of duplicating')
        self.assertEqual((bob.name, bob.phone), ('Bob Solo', '+32 470 99 99 99'))
        lead = self.record('deals', self.deal)
        self.assertEqual((lead.name, lead.expected_revenue, str(lead.date_deadline), lead.partner_id, lead.type, lead.user_id),
                         ('Acme renewal', 12000.0, '2026-04-30', jane, 'opportunity', self.admin))
        self.assertEqual(self.jobs(state='done').mapped('result').count('created'), 3)
        self.assertEqual(lead.hubspot_id, self.deal)
        self.assertIn('/record/0-3/', lead.hubspot_url)
        # nothing changed: nothing queued
        before = len(self.jobs())
        self.account.action_import_now()
        self.assertEqual(len(self.jobs()) - before, 0)
        # a change in HubSpot is imported on the next run, and only that one
        self.fake.change('contacts', self.jane, jobtitle='CEO')
        self.fake.change('deals', self.deal, dealstage='closedwon')
        self.account.action_import_now()
        self.assertEqual(jane.function, 'CEO')
        self.assertEqual(lead.stage_id, self.won_stage)
        self.fake.change('deals', self.deal, dealstage='closedlost')
        self.account.action_import_now()
        self.assertFalse(lead.active, 'closed lost -> lost in Odoo')
        self.assertEqual(lead.probability, 0)

    def test_deals_as_leads_and_associations_on_demand(self):
        self._crm()
        self.account.deal_type = 'lead'
        self.enable('deals')
        self.account.action_import_now()
        lead = self.record('deals', self.deal)
        self.assertEqual(lead.type, 'lead')
        self.assertEqual(lead.partner_id.name, 'Jane Doe', 'missing contact imported on the fly')
        self.assertEqual(lead.partner_id.parent_id.name, 'Acme Corp')

    def test_products_quotes_invoices(self):
        f = self.fake
        p1 = f.add('products', {'name': 'Consulting day', 'price': '800', 'hs_sku': 'CONS-1', 'hs_cost_of_goods_sold': '300'})
        company = f.add('companies', {'name': 'Globex', 'domain': 'globex.example.com'})
        item1 = f.add('line_items', {'name': 'Consulting day', 'quantity': '3', 'price': '750', 'hs_product_id': p1,
                                     'hs_discount_percentage': '10'})
        item2 = f.add('line_items', {'name': 'Travel costs', 'quantity': '1', 'price': '120'})
        quote = f.add('quotes', {'hs_title': 'Globex Q-2026-01', 'hs_expiration_date': '2026-05-31', 'hs_status': 'DRAFT'},
                      [('companies', company), ('line_items', item1), ('line_items', item2)])
        item3 = f.add('line_items', {'name': 'Consulting day', 'quantity': '2', 'price': '800', 'hs_product_id': p1})
        invoice = f.add('invoices', {'hs_number': 'HS-INV-7', 'hs_invoice_date': '2026-03-10', 'hs_due_date': '2026-04-09'},
                        [('companies', company), ('line_items', item3)])
        self.enable('products', 'companies', 'quotes', 'invoices')
        self.account.action_import_now()
        product = self.record('products', p1)
        self.assertEqual((product.name, product.list_price, product.default_code, product.standard_price),
                         ('Consulting day', 800.0, 'CONS-1', 300.0))
        order = self.record('quotes', quote)
        self.assertEqual(order.partner_id.name, 'Globex')
        self.assertEqual(order.client_order_ref, 'Globex Q-2026-01')
        self.assertEqual(str(order.validity_date), '2026-05-31')
        lines = order.order_line.sorted('price_unit')
        self.assertEqual(lines.mapped('product_uom_qty'), [1.0, 3.0])
        self.assertEqual(lines[1].product_id, product.product_variant_id)
        self.assertEqual(lines[1].discount, 10)
        self.assertEqual(lines[0].product_id, self.account.fallback_product_id, 'line without product')
        move = self.record('invoices', invoice)
        self.assertEqual((move.move_type, move.state, move.ref, str(move.invoice_date)),
                         ('out_invoice', 'draft', 'HS-INV-7', '2026-03-10'))
        self.assertEqual(move.invoice_line_ids.quantity, 2)
        # confirmed orders are not changed by HubSpot any more
        order.action_confirm()
        f.change('quotes', quote, hs_title='Changed')
        self.account.action_import_now()
        self.assertEqual(order.client_order_ref, 'Globex Q-2026-01')

    def test_engagements(self):
        self._crm()
        f = self.fake
        note = f.add('notes', {'hs_note_body': '<p>Called Jane, <b>budget OK</b>.</p>', 'hs_timestamp': '2026-03-03T10:00:00Z',
                               'hubspot_owner_id': '501'}, [('contacts', self.jane)])
        task = f.add('tasks', {'hs_task_subject': 'Send the proposal', 'hs_task_body': 'Before Friday',
                               'hs_task_status': 'NOT_STARTED', 'hs_timestamp': '2026-03-06T09:00:00Z',
                               'hubspot_owner_id': '501'}, [('deals', self.deal)])
        meeting = f.add('meetings', {'hs_meeting_title': 'Kick-off', 'hs_meeting_start_time': '2026-03-09T13:00:00Z',
                                     'hs_meeting_end_time': '2026-03-09T14:30:00Z', 'hs_meeting_location': 'Brussels office',
                                     'hubspot_owner_id': '501'}, [('contacts', self.jane), ('deals', self.deal)])
        email = f.add('emails', {'hs_email_subject': 'Your offer', 'hs_email_text': 'Thanks, looks good.',
                                 'hs_email_direction': 'INCOMING_EMAIL', 'hs_timestamp': '2026-03-04T08:00:00Z'},
                      [('contacts', self.jane)])
        orphan = f.add('notes', {'hs_note_body': 'Nobody', 'hs_timestamp': '2026-03-03T10:00:00Z'})
        self.enable('companies', 'contacts', 'deals', 'notes', 'tasks', 'meetings', 'emails')
        self.account.action_import_now()
        jane = self.record('contacts', self.jane)
        lead = self.record('deals', self.deal)
        message = self.record('notes', note)
        self.assertEqual((message.model, message.res_id), ('res.partner', jane.id))
        self.assertIn('budget OK', message.body)
        self.assertEqual(str(message.date), '2026-03-03 10:00:00')
        activity = self.record('tasks', task)
        self.assertEqual((activity.res_model, activity.res_id, activity.summary, activity.user_id, str(activity.date_deadline)),
                         ('crm.lead', lead.id, 'Send the proposal', self.admin, '2026-03-06'))
        event = self.record('meetings', meeting)
        self.assertEqual((event.name, event.location, str(event.start), str(event.stop)),
                         ('Kick-off', 'Brussels office', '2026-03-09 13:00:00', '2026-03-09 14:30:00'))
        self.assertIn(jane, event.partner_ids)
        self.assertEqual((event.res_model, event.res_id), ('crm.lead', lead.id), 'linked to the deal first')
        mail = self.record('emails', email)
        self.assertEqual(mail.subject, 'Your offer')
        self.assertEqual(mail.author_id, jane, 'incoming e-mail written by the contact')
        self.assertEqual(self.jobs(hubspot_id=orphan).state, 'skipped')
        # task completed in HubSpot -> done in Odoo
        f.change('tasks', task, hs_task_status='COMPLETED')
        self.account.action_import_now()
        self.assertFalse(activity.active)

    def test_custom_mapping_and_conflicts(self):
        self._crm()
        ref_field = self.env['ir.model.fields']._get('res.partner', 'ref')
        self.env['hubspot.field.mapping'].create({'account_id': self.account.id, 'object_type': 'contacts',
                                                  'field_id': ref_field.id, 'hubspot_property': 'customer_reference'})
        self.fake.change('contacts', self.jane, customer_reference='CUST-77')
        self.enable('companies', 'contacts')
        self.account.action_import_now()
        jane = self.record('contacts', self.jane)
        self.assertEqual(jane.ref, 'CUST-77')
        # both sides changed: Odoo wins -> the import leaves the local value
        self.account.conflict_policy = 'odoo'
        jane.function = 'Head of IT'
        self.fake.change('contacts', self.jane, jobtitle='HubSpot title')
        self.account.action_import_now()
        self.assertEqual(jane.function, 'Head of IT')
        # HubSpot wins
        self.account.conflict_policy = 'hubspot'
        self.fake.change('contacts', self.jane, jobtitle='HubSpot title 2')
        self.account.action_import_now()
        self.assertEqual(jane.function, 'HubSpot title 2')

    def test_description_html(self):
        company = self.fake.add('companies', {'name': 'Initech', 'description': 'Printers & <staplers>'})
        self.enable('companies')
        self.account.action_import_now()
        partner = self.record('companies', company)
        self.assertIn('&lt;staplers&gt;', str(partner.comment), 'plain text is escaped')
        self.assertIsInstance(partner.comment, Markup)
