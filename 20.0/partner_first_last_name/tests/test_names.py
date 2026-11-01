from odoo.tests import Form, HttpCase, TransactionCase, tagged

from ..models.name_tools import join_name, split_name


@tagged('post_install', '-at_install')
class TestNameTools(TransactionCase):

    def test_split_and_join(self):
        cases = [
            ('John Smith', 'first_last', False, ('John', '', 'Smith')),
            ('Jean Paul Sartre', 'first_last', False, ('Jean Paul', '', 'Sartre')),
            ('Jean Paul Sartre', 'first_last', True, ('Jean', 'Paul', 'Sartre')),
            ('Ludwig van Beethoven', 'first_last', False, ('Ludwig', '', 'van Beethoven')),
            ('Maria de la Cruz', 'first_last', False, ('Maria', '', 'de la Cruz')),
            ('Smith John', 'last_first', False, ('John', '', 'Smith')),
            ('van Beethoven Ludwig', 'last_first', False, ('Ludwig', '', 'van Beethoven')),
            ('Smith, John Paul', 'last_comma_first', True, ('John', 'Paul', 'Smith')),
            ('Smith, John', 'first_last', False, ('John', '', 'Smith')),
            ('Madonna', 'first_last', False, ('Madonna', '', '')),
            ('  John   Smith ', 'first_last', False, ('John', '', 'Smith')),
            ('', 'first_last', False, ('', '', '')),
        ]
        for name, order, middle, expected in cases:
            with self.subTest(name=name, order=order):
                self.assertEqual(split_name(name, order, middle), expected)
        self.assertEqual(join_name('John', 'Paul', 'Smith', 'first_last'), 'John Paul Smith')
        self.assertEqual(join_name('John', 'Paul', 'Smith', 'last_first'), 'Smith John Paul')
        self.assertEqual(join_name('John', '', 'Smith', 'last_comma_first'), 'Smith, John')
        self.assertEqual(join_name('', '', 'Smith', 'last_comma_first'), 'Smith')
        self.assertEqual(join_name(' John ', None, False), 'John')


@tagged('post_install', '-at_install')
class TestPartnerNames(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ICP = cls.env['ir.config_parameter'].sudo()
        cls.ICP.set_str('partner_first_last_name.order', 'first_last')
        cls.ICP.set_bool('partner_first_last_name.middle', False)
        cls.Partner = cls.env['res.partner']

    def test_create_and_write(self):
        partner = self.Partner.create({'first_name': ' Anna ', 'last_name': 'Peeters'})
        self.assertEqual(partner.name, 'Anna Peeters')
        self.assertEqual(partner.first_name, 'Anna')
        partner.last_name = 'Janssens'
        self.assertEqual(partner.name, 'Anna Janssens')
        partner.name = 'Marie Claire Dubois'
        self.assertEqual((partner.first_name, partner.middle_name, partner.last_name),
                         ('Marie Claire', False, 'Dubois'))
        # a contact of a company created with a plain name (import, quick create, CRM)
        acme = self.Partner.create({'name': 'Acme Industries'})
        self.assertFalse(acme.first_name or acme.last_name, 'a lone name may be a company: not split')
        acme.write({'name': 'Acme Group'})
        self.assertFalse(acme.first_name)
        imported = self.Partner.create({'name': 'Ludwig van Beethoven', 'parent_id': acme.id})
        self.assertEqual((imported.first_name, imported.last_name), ('Ludwig', 'van Beethoven'))
        # companies (VAT) are left alone even with a parent-less name change
        company = self.Partner.create({'name': 'Beta NV', 'vat': 'BE0477472701'})
        if company.is_company:
            company.write({'name': 'Beta Group NV'})
            self.assertFalse(company.first_name)
        # the Contacts app opens new records as companies (default_is_company): the parts still make the name
        from_app = self.Partner.with_context(default_is_company=True).create({'first_name': 'Ann', 'last_name': 'Lee'})
        self.assertEqual(from_app.name, 'Ann Lee')
        # contacts of a company with a VAT number share its VAT but are people
        vat_company = self.Partner.create({'name': 'Gamma BV', 'vat': 'BE0477472701'})
        employee = self.Partner.create({'name': 'Jan Peeters', 'parent_id': vat_company.id})
        self.assertEqual((employee.first_name, employee.last_name), ('Jan', 'Peeters'))
        employee.last_name = 'Claes'
        self.assertEqual(employee.name, 'Jan Claes')
        # several records at once keep their own other parts
        people = self.Partner.create([{'first_name': 'Tom', 'last_name': 'Maes'},
                                      {'first_name': 'Kris', 'last_name': 'Wouters'}])
        people.write({'last_name': 'Peeters'})
        self.assertEqual(people.mapped('name'), ['Tom Peeters', 'Kris Peeters'])

    def test_orders_and_middle_names(self):
        self.ICP.set_str('partner_first_last_name.order', 'last_comma_first')
        self.ICP.set_bool('partner_first_last_name.middle', True)
        partner = self.Partner.create({'first_name': 'John', 'middle_name': 'Paul', 'last_name': 'Smith'})
        self.assertEqual(partner.name, 'Smith, John Paul')
        self.assertTrue(partner.partner_names_show_middle)
        partner.name = 'Jones, Mary Ann'  # has parts already: split
        self.assertEqual((partner.first_name, partner.middle_name, partner.last_name), ('Mary', 'Ann', 'Jones'))
        self.ICP.set_str('partner_first_last_name.order', 'last_first')
        partner2 = self.Partner.create({'name': 'Martin Sophie', 'parent_id': partner.id})
        self.assertEqual((partner2.first_name, partner2.last_name), ('Sophie', 'Martin'))

    def test_apply_order_and_fill_missing(self):
        acme = self.Partner.create({'name': 'Acme'})
        old = self.Partner.with_context(partner_names_skip=True).create({'name': 'Grace Kim', 'parent_id': acme.id})
        self.assertFalse(old.first_name)
        # the settings form saves the new order before running the button: the old order is remembered
        self.ICP.set_str('partner_first_last_name.order', 'last_first')
        settings = self.env['res.config.settings'].create({'partner_names_order': 'last_first'})
        self.assertEqual(settings.partner_names_preview, 'Smith John')
        settings.action_partner_names_apply()
        self.assertEqual((old.first_name, old.last_name), ('Grace', 'Kim'))
        self.assertEqual(old.name, 'Kim Grace')
        self.assertEqual(self.ICP.get_str('partner_first_last_name.order'), 'last_first')
        self.assertEqual(self.ICP.get_str('partner_first_last_name.applied_order'), 'last_first')
        # list action
        odd = self.Partner.with_context(partner_names_skip=True).create(
            {'name': 'Lee Ann', 'first_name': 'X', 'last_name': 'Y', 'parent_id': acme.id})
        odd.action_partner_names_split()
        self.assertEqual((odd.first_name, odd.last_name), ('Ann', 'Lee'))

    def test_form_onchanges(self):
        with Form(self.Partner) as form:
            form.first_name = 'Hannah'
            form.last_name = 'Okafor'
            self.assertEqual(form.name, 'Hannah Okafor')
            form.name = 'Hannah Grace Okafor'  # the contact has parts: the new name is split
            self.assertEqual(form.first_name, 'Hannah Grace')
            self.assertEqual(form.last_name, 'Okafor')
        partner = form.save()
        self.assertEqual(partner.name, 'Hannah Grace Okafor')

    def test_users(self):
        user = self.env['res.users'].create({'first_name': 'Wendy', 'last_name': 'Agent', 'login': 'wendy'})
        self.assertEqual(user.name, 'Wendy Agent')
        self.assertEqual(user.partner_id.last_name, 'Agent')
        user.with_user(user).write({'last_name': 'Smith'})
        self.assertEqual(user.name, 'Wendy Smith')
        other = self.env['res.users'].create({'name': 'Lucas Moreau', 'login': 'lucas'})
        self.assertEqual((other.first_name, other.last_name), ('Lucas', 'Moreau'))

    def test_crm_lead(self):
        lead = self.env['crm.lead'].create({'name': 'Boiler', 'type': 'lead', 'contact_name': 'Marc Dubois',
                                            'email_from': 'marc@example.com'})
        self.assertEqual((lead.contact_first_name, lead.contact_last_name), ('Marc', 'Dubois'))
        lead.contact_first_name = 'Marcel'
        self.assertEqual(lead.contact_name, 'Marcel Dubois')
        partner = lead._handle_partner_assignment(create_missing=True) or lead.partner_id
        partner = lead.partner_id
        self.assertEqual((partner.first_name, partner.last_name, partner.name), ('Marcel', 'Dubois', 'Marcel Dubois'))
        # the contact fields of the lead form are in debug mode in Odoo 20: check the onchange directly
        new_lead = self.env['crm.lead'].new({'name': 'Heat pump', 'contact_first_name': 'Lotte',
                                             'contact_last_name': 'Janssens'})
        new_lead._onchange_lead_names_parts()
        self.assertEqual(new_lead.contact_name, 'Lotte Janssens')

    def test_signup(self):
        self.env['ir.config_parameter'].sudo().set_str('auth_signup.invitation_scope', 'b2c')
        response = self.url_open('/web/signup')
        self.assertIn('name="first_name"', response.text)
        self.assertNotIn('name="name"', response.text)
        self.start_tour('/web/signup', 'partner_names_signup_tour')
        user = self.env['res.users'].search([('login', '=', 'lotte@example.com')])
        self.assertEqual(user.name, 'Lotte Janssens')
        self.assertEqual((user.first_name, user.last_name), ('Lotte', 'Janssens'))

    def test_post_init_hook(self):
        acme = self.Partner.create({'name': 'Acme'})
        legacy = self.Partner.with_context(partner_names_skip=True).create(
            {'name': 'Youssef El Amrani', 'parent_id': acme.id})
        lone = self.Partner.with_context(partner_names_skip=True).create({'name': 'Lone Company'})
        from .. import _post_init_split_names
        _post_init_split_names(self.env)
        self.assertEqual((legacy.first_name, legacy.last_name), ('Youssef', 'El Amrani'))
        self.assertFalse(lone.first_name, 'names without a company or user are not guessed in Odoo 20')
        self.assertFalse(acme.first_name)
