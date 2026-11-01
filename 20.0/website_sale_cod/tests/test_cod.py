from odoo.exceptions import AccessError, UserError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.delivery.tests.cash_on_delivery_common import CashOnDeliveryCommon


class CodSetup:

    @classmethod
    def _cod_setup(cls):
        env = cls.env
        cls.furniture = env['product.category'].create({'name': 'Furniture'})
        cls.made_to_order = env['product.category'].create({'name': 'Made to order', 'parent_id': cls.furniture.id})
        cls.chair = env['product.product'].create({'name': 'Oak chair', 'list_price': 120.0, 'type': 'consu',
                                                   'categ_id': cls.furniture.id, 'taxes_id': [(5, 0, 0)]})
        cls.custom_table = env['product.product'].create({'name': 'Custom table', 'list_price': 900.0,
                                                          'type': 'consu', 'categ_id': cls.made_to_order.id,
                                                          'taxes_id': [(5, 0, 0)]})
        cls.cash_journal = env['account.journal'].search([('type', '=', 'cash'),
                                                          ('company_id', '=', env.company.id)], limit=1) or \
            env['account.journal'].create({'name': 'Cash', 'code': 'CSH1', 'type': 'cash'})


@tagged('post_install', '-at_install')
class TestCod(CashOnDeliveryCommon, CodSetup):
    # Odoo 20 commons run as a restricted test user by default; these tests set up providers and journals
    _test_user_groups = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._cod_setup()
        cls.free_delivery.allow_cash_on_delivery = True
        cls.cod_provider.write({'cod_journal_id': cls.cash_journal.id, 'cod_otp': True, 'cod_otp_length': 6})
        cls.order = cls.sale_order
        cls.order.write({'carrier_id': cls.free_delivery.id,
                         'order_line': [(0, 0, {'product_id': cls.chair.id, 'product_uom_qty': 2})]})
        cls.driver = new_test_user(cls.env, 'cod_driver', groups='base.group_user,website_sale_cod.group_cod_driver',
                                   name='Dirk Driver')
        cls.manager = new_test_user(cls.env, 'cod_manager', groups='sales_team.group_sale_manager,'
                                                                    'account.group_account_invoice',
                                    name='Sam Sales')

    @property
    def total(self):
        return self.order.amount_total

    def _pay_cod(self, order=None):
        self._disable_post_process_patcher()
        order = order or self.order
        tx = self._create_cod_transaction(order)
        with mute_logger('odoo.addons.sale.models.payment_transaction'):
            self._run_post_processing()
        return tx

    def _compatible(self, order):
        return self.env['payment.provider'].sudo()._find_available_providers(
            self.env.company.id, order.partner_id.id, order.amount_total, currency_id=order.currency_id.id,
            sale_order_id=order.id)

    def test_availability_rules(self):
        self.assertIn(self.cod_provider, self._compatible(self.order))
        self.cod_provider.minimum_amount = self.total + 100  # Odoo 20 has a native minimum amount
        report = {}
        providers = self.env['payment.provider'].sudo()._find_available_providers(
            self.env.company.id, self.partner.id, self.order.amount_total, currency_id=self.order.currency_id.id,
            sale_order_id=self.order.id, report=report)
        self.assertNotIn(self.cod_provider, providers)
        self.cod_provider.minimum_amount = 0
        # a product of a sub-category of an excluded category
        self.cod_provider.cod_excluded_categ_ids = self.furniture
        custom = self.order.copy({'order_line': [(0, 0, {'product_id': self.custom_table.id})]})
        custom.carrier_id = self.free_delivery
        self.assertNotIn(self.cod_provider, self._compatible(custom))
        self.cod_provider.cod_excluded_categ_ids = self.made_to_order
        self.assertNotIn(self.cod_provider, self._compatible(custom))
        self.assertIn(self.cod_provider, self._compatible(self.order))
        # Odoo's own rule still applies: the delivery method must accept cash
        self.free_delivery.allow_cash_on_delivery = False
        self.assertNotIn(self.cod_provider, self._compatible(self.order))

    def test_order_confirmed_with_code_and_collection(self):
        tx = self._pay_cod()
        self.assertEqual(self.order.state, 'sale')
        self.assertRegex(self.order.cod_otp, r'^\d{6}$')
        collection = self.order.cod_collection_ids
        self.assertRecordValues(collection, [{'state': 'draft', 'amount_due': self.total, 'transaction_id': tx.id}])
        self.assertGreater(self.total, 0)
        self.assertTrue(collection.name.startswith('COD/'))
        self.assertTrue(self.order.is_cod)
        self.assertIn(self.order, self.env['sale.order'].search([('is_cod', '=', True)]))
        message = self.order.message_ids.filtered(lambda m: 'your delivery code' in (m.subject or ''))
        self.assertTrue(message)
        self.assertIn(self.order.cod_otp, message.body)
        # post-processing again does not create a second collection
        self._run_post_processing()
        self.assertEqual(len(self.order.cod_collection_ids), 1)

    def test_collect_with_code(self):
        self._pay_cod()
        collection = self.order.cod_collection_ids
        Wizard = self.env['sale.cod.collect.wizard'].with_user(self.driver)
        wizard = Wizard.with_context(default_collection_id=collection.id).create({'code': '000000'})
        self.assertEqual(wizard.amount, self.total)
        if self.order.cod_otp == '000000':
            wizard.code = '111111'
        result = wizard.action_confirm()
        self.assertEqual(result['res_model'], 'sale.cod.collect.wizard', 'reopened with the error')
        self.assertIn('Wrong delivery code', wizard.error)
        self.assertEqual(collection.otp_attempts, 1)
        self.assertEqual(collection.state, 'draft')
        wizard.write({'code': self.order.cod_otp, 'amount': 200.0})
        with self.assertRaises(UserError):
            wizard.action_confirm()
        wizard.amount = self.total
        wizard.action_confirm()
        self.assertRecordValues(collection, [{'state': 'collected', 'amount_collected': self.total,
                                              'driver_id': self.driver.id}])
        self.assertTrue(collection.date_collected)

    def test_attempt_limit_and_new_code(self):
        self._pay_cod()
        collection = self.order.cod_collection_ids
        for _i in range(5):
            self.assertFalse(collection._cod_check_code('wrong'))
        with self.assertRaises(UserError):
            collection._cod_check_code(self.order.cod_otp)
        old = self.order.cod_otp
        collection.action_new_code()
        self.assertEqual(collection.otp_attempts, 0)
        self.assertNotEqual(self.order.cod_otp, old)
        self.assertTrue(collection._cod_check_code(self.order.cod_otp))

    def test_deposit_invoices_and_pays(self):
        tx = self._pay_cod()
        collection = self.order.cod_collection_ids
        collection._cod_collect(self.order.cod_otp, self.total, driver=self.driver)
        with self.assertRaises(UserError):
            collection.with_user(self.driver).action_deposit()
        collection.with_user(self.manager).action_deposit()
        self.assertEqual(collection.state, 'done')
        invoice = self.order.invoice_ids
        self.assertEqual(invoice.state, 'posted')
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))
        self.assertEqual(collection.payment_id.journal_id, self.cash_journal)
        self.assertEqual(collection.payment_id.amount, self.total)
        self.assertEqual(tx.state, 'done')
        self.assertTrue(tx.is_post_processed)
        self.assertEqual(tx.payment_id, collection.payment_id)
        # Odoo's post-processing cron does not pay a second time
        payments_before = self.env['account.payment'].search_count([])
        self._run_post_processing()
        self.assertEqual(self.env['account.payment'].search_count([]), payments_before)
        self.assertIn(invoice.payment_state, ('paid', 'in_payment'))

    def test_cancel_and_reset(self):
        tx = self._pay_cod()
        collection = self.order.cod_collection_ids
        wizard = self.env['sale.cod.cancel.wizard'].with_user(self.manager).create({
            'collection_ids': [(6, 0, collection.ids)], 'reason': 'absent', 'details': 'Nobody at 18:00'})
        wizard.action_cancel()
        self.assertEqual(collection.state, 'cancel')
        self.assertIn('Customer not at home. Nobody at 18:00', collection.cancel_reason)
        self.assertEqual(tx.state, 'cancel')
        collection.action_reset()
        self.assertEqual(collection.state, 'draft')

    def test_without_code(self):
        self.cod_provider.cod_otp = False
        self._pay_cod()
        collection = self.order.cod_collection_ids
        self.assertFalse(self.order.cod_otp)
        wizard = self.env['sale.cod.collect.wizard'].with_context(default_collection_id=collection.id).create({})
        self.assertFalse(wizard.otp_required)
        wizard.action_confirm()
        self.assertEqual(collection.state, 'collected')

    def test_driver_rights(self):
        self._pay_cod()
        collection = self.order.cod_collection_ids
        Collection = self.env['sale.cod.collection'].with_user(self.driver)
        self.assertEqual(Collection.search([]), collection)
        collection.driver_id = self.manager
        self.assertFalse(Collection.search([]), 'collections of another driver are hidden')
        collection.driver_id = self.driver
        data = collection.with_user(self.driver).read(['customer_name', 'delivery_address', 'amount_due'])[0]
        self.assertEqual(data['amount_due'], self.total)
        with self.assertRaises(AccessError):
            self.order.with_user(self.driver).read(['cod_otp'])
        report = self.env['ir.actions.report']._render_qweb_html('website_sale_cod.report_cod_collection',
                                                                  collection.ids)[0]
        self.assertIn(collection.name.encode(), report)


@tagged('post_install', '-at_install')
class TestCodPortal(HttpCase, CodSetup):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._cod_setup()
        cls.portal = new_test_user(cls.env, 'portalcod', groups='base.group_portal', name='Paula Portal')
        cls.order = cls.env['sale.order'].create({
            'partner_id': cls.portal.partner_id.id,
            'order_line': [(0, 0, {'product_id': cls.chair.id, 'product_uom_qty': 1})],
        })
        cls.order.action_confirm()
        cls.order.cod_otp = '482913'
        cls.collection = cls.env['sale.cod.collection'].create({'order_id': cls.order.id, 'amount_due': 120.0})
        cls.driver = new_test_user(cls.env, 'driver2', groups='base.group_user,website_sale_cod.group_cod_driver',
                                   name='Dirk Driver')

    def test_portal_shows_code(self):
        self.authenticate('portalcod', 'portalcod')
        response = self.url_open(f'/my/orders/{self.order.id}')
        self.assertEqual(response.status_code, 200)
        self.assertIn('o_cod_code_box', response.text)
        self.assertIn('482913', response.text)
        self.collection.state = 'collected'
        response = self.url_open(f'/my/orders/{self.order.id}')
        self.assertNotIn('482913', response.text, 'the code disappears once used')

    def test_tour_driver_collects(self):
        self.start_tour(f'/odoo/action-website_sale_cod.action_sale_cod_collection/{self.collection.id}',
                        'website_sale_cod_collect_tour', login='driver2')
        self.assertEqual(self.collection.state, 'collected')
        self.assertEqual(self.collection.driver_id.login, 'driver2')
