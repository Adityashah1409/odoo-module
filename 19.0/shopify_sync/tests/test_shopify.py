import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

from odoo.tests import HttpCase, TransactionCase, tagged

from ..models import queries
from ..models.shopify_instance import ShopifyError
from .common import MUG, ShopifyCase, make_order


@tagged('post_install', '-at_install')
class TestShopifySync(ShopifyCase):

    def test_connection_and_locations(self):
        self.instance.action_test_connection()
        self.assertEqual(self.instance.state, 'connected')
        self.assertEqual(self.instance.shop_currency, 'USD')
        self.assertEqual(self.instance.location_ids.mapped('name'), ['Main warehouse'])
        self.assertEqual(self.instance.location_ids.warehouse_id, self.warehouse)

    def test_import_products_creates_variants(self):
        self.instance.action_import_products()
        maps = self.instance.product_map_ids
        self.assertEqual(len(maps), 3)
        tshirt = maps.filtered(lambda m: m.sku == 'TSHIRT-M').product_id
        self.assertEqual(tshirt.product_tmpl_id.name, 'Organic T-shirt')
        self.assertEqual(len(tshirt.product_tmpl_id.product_variant_ids), 2)
        self.assertEqual(tshirt.product_template_attribute_value_ids.name, 'M')
        self.assertEqual(tshirt.default_code, 'TSHIRT-M')
        mug = maps.filtered(lambda m: m.sku == 'MUG-01')
        self.assertEqual(mug.inventory_item_id, 'gid://shopify/InventoryItem/2001')
        self.assertTrue(self.instance.product_import_from)

    def test_import_products_matches_existing_sku(self):
        mug = self.env['product.product'].create({'name': 'Our mug', 'default_code': 'MUG-01', 'is_storable': True})
        self.instance.action_import_products()
        mapping = self.instance.product_map_ids.filtered(lambda m: m.sku == 'MUG-01')
        self.assertEqual(mapping.product_id, mug)
        self.instance.action_import_products()
        self.assertEqual(len(self.instance.product_map_ids), 3, "re-import does not duplicate mappings")

    def test_missing_products_without_auto_create_fail(self):
        self.instance.create_missing_products = False
        self.instance.action_import_products()
        failed = self.env['shopify.queue'].search([('instance_id', '=', self.instance.id), ('state', '=', 'failed')])
        self.assertEqual(len(failed), 2)
        self.assertIn('TSHIRT-S', failed.filtered(lambda q: q.name == 'Organic T-shirt').message)

    def test_import_customers_matches_by_email(self):
        partner = self.env['res.partner'].create({'name': 'A. Lee', 'email': 'ANN@example.com'})
        self.instance.action_import_customers()
        mapping = self.env['shopify.customer.map'].search([('instance_id', '=', self.instance.id)])
        self.assertEqual(mapping.partner_id, partner)
        self.assertEqual(partner.city, 'Austin')
        self.assertEqual(partner.country_id.code, 'US')

    def test_import_order_full_workflow(self):
        self.instance.auto_create_invoice = True
        self.instance.action_import_products()
        self.instance.action_import_orders()
        order = self.instance.order_ids
        self.assertEqual(len(order), 1)
        self.assertEqual(order.shopify_order_name, '#1001')
        self.assertEqual(order.client_order_ref, '#1001')
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.partner_id.email, 'ann@example.com')
        product_line = order.order_line.filtered(lambda l: l.product_id.default_code == 'TSHIRT-S')
        self.assertEqual((product_line.product_uom_qty, product_line.price_unit), (2, 25))
        self.assertEqual(sorted(order.order_line.mapped('price_unit')), [-5.0, 7.5, 25.0])
        self.assertEqual(order.shopify_financial_status, 'PAID')
        self.assertEqual(order.invoice_ids.state, 'posted')
        self.assertTrue(order.picking_ids)
        # importing again does not duplicate
        self.instance.order_import_from = False
        self.instance.action_import_orders()
        self.assertEqual(len(self.instance.order_ids), 1)

    def test_order_status_filter_and_cancellation(self):
        self.shopify.orders = [make_order(1002, status='PENDING')]
        self.instance.action_import_orders()
        self.assertFalse(self.instance.order_ids)
        line = self.env['shopify.queue'].search([('shopify_id', '=', 'gid://shopify/Order/1002')])
        self.assertEqual(line.state, 'skipped')

        self.shopify.orders = [make_order(1003)]
        self.instance.action_import_orders()
        order = self.instance.order_ids
        self.assertEqual(order.state, 'sale')
        self.shopify.orders = [make_order(1003, cancelled=True)]
        self.instance.order_import_from = False
        self.instance.action_import_orders()
        self.assertEqual(order.state, 'cancel')

    def test_unknown_sku_fails_then_retry(self):
        self.instance.create_missing_products = False
        self.shopify.orders = [make_order(1004, sku='NEW-SKU', variant='gid://shopify/ProductVariant/555')]
        self.instance.action_import_orders()
        line = self.env['shopify.queue'].search([('shopify_id', '=', 'gid://shopify/Order/1004')])
        self.assertEqual(line.state, 'failed')
        self.assertIn('NEW-SKU', line.message)
        self.env['product.product'].create({'name': 'New product', 'default_code': 'NEW-SKU'})
        line.action_retry()
        self.assertEqual(line.state, 'done')
        self.assertEqual(line.res_model, 'sale.order')

    def test_currency_mismatch(self):
        eur = self.env.ref('base.EUR')
        eur.active = True
        self.instance.pricelist_id = self.env['product.pricelist'].create({'name': 'EUR', 'currency_id': eur.id})
        self.instance.action_import_orders()
        line = self.env['shopify.queue'].search([('shopify_id', '=', 'gid://shopify/Order/1001')])
        self.assertEqual(line.state, 'failed')
        self.assertIn('currency', line.message)

    def test_export_stock(self):
        self.instance.action_test_connection()
        self.instance.action_import_products()
        mug = self.instance.product_map_ids.filtered(lambda m: m.sku == 'MUG-01').product_id
        self.env['stock.quant']._update_available_quantity(mug, self.warehouse.lot_stock_id, 7)
        self.instance.action_export_stock()
        sent = self.shopify.mutations(queries.INVENTORY_SET)[0]['input']['quantities']
        mug_qty = next(q for q in sent if q['inventoryItemId'] == 'gid://shopify/InventoryItem/2001')
        self.assertEqual(mug_qty, {'inventoryItemId': 'gid://shopify/InventoryItem/2001',
                                   'locationId': 'gid://shopify/Location/1', 'quantity': 7})
        self.assertEqual(len(sent), 3)

    def test_delivery_creates_fulfillment(self):
        self.instance.action_import_products()
        self.instance.action_import_orders()
        order = self.instance.order_ids
        picking = order.picking_ids
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        fulfillment = self.shopify.mutations(queries.FULFILLMENT_CREATE)[0]['fulfillment']
        self.assertEqual(fulfillment['lineItemsByFulfillmentOrder'], [{'fulfillmentOrderId': 'gid://shopify/FulfillmentOrder/9'}])
        self.assertEqual(order.shopify_fulfillment_status, 'FULFILLED')

    def test_export_product(self):
        size = self.env['product.attribute'].create({'name': 'Color', 'value_ids': [(0, 0, {'name': 'Red'}), (0, 0, {'name': 'Blue'})]})
        template = self.env['product.template'].create({
            'name': 'Cap', 'list_price': 15, 'is_storable': True,
            'attribute_line_ids': [(0, 0, {'attribute_id': size.id, 'value_ids': [(6, 0, size.value_ids.ids)]})],
        })
        wizard = self.env['shopify.export.product.wizard'].with_context(
            active_model='product.template', active_ids=template.ids).create({'instance_id': self.instance.id})
        wizard.action_export()
        sent = self.shopify.mutations(queries.PRODUCT_SET)[0]['input']
        self.assertEqual(sent['title'], 'Cap')
        self.assertEqual(sent['productOptions'], [{'name': 'Color', 'values': [{'name': 'Red'}, {'name': 'Blue'}]}])
        self.assertEqual(len(sent['variants']), 2)
        self.assertEqual(len(self.instance.product_map_ids.filtered(lambda m: m.product_tmpl_id == template)), 2)


@tagged('post_install', '-at_install')
class TestShopifyWebhook(HttpCase, ShopifyCase):

    def post(self, body, secret='whsec_test', topic='orders/create'):
        raw = json.dumps(body).encode()
        signature = base64.b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()).decode()
        return self.url_open(f'/shopify_sync/webhook/{self.instance.id}', data=raw, headers={
            'X-Shopify-Hmac-Sha256': signature, 'X-Shopify-Topic': topic, 'Content-Type': 'application/json'})

    def test_webhook_signature_and_queue(self):
        response = self.post({'id': 1001, 'name': '#1001'}, secret='wrong')
        self.assertEqual(response.status_code, 401)
        response = self.post({'id': 1001, 'name': '#1001'})
        self.assertEqual(response.status_code, 200)
        line = self.env['shopify.queue'].search([('instance_id', '=', self.instance.id)])
        self.assertEqual((line.source, line.shopify_id), ('webhook', 'gid://shopify/Order/1001'))
        self.env['shopify.queue']._cron_process()
        self.assertEqual(line.state, 'done')
        self.assertEqual(self.instance.order_ids.shopify_order_name, '#1001')

    def test_webhook_bad_payload(self):
        # signed but not JSON / not an object: rejected with 400, nothing queued
        raw = b'not json'
        signature = base64.b64encode(hmac.new(b'whsec_test', raw, hashlib.sha256).digest()).decode()
        response = self.url_open(f'/shopify_sync/webhook/{self.instance.id}', data=raw, headers={
            'X-Shopify-Hmac-Sha256': signature, 'X-Shopify-Topic': 'orders/create'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post([1, 2]).status_code, 400)
        self.assertFalse(self.env['shopify.queue'].search([('instance_id', '=', self.instance.id)]))

    def test_webhook_product(self):
        payload = {'id': 20, 'title': 'Coffee Mug', 'options': [{'name': 'Title', 'values': ['Default Title']}],
                   'variants': [{'id': 201, 'title': 'Default Title', 'sku': 'MUG-01', 'price': '12.00',
                                 'inventory_item_id': 2001, 'option1': 'Default Title'}]}
        self.assertEqual(self.post(payload, topic='products/update').status_code, 200)
        self.env['shopify.queue']._cron_process()
        mapping = self.instance.product_map_ids
        self.assertEqual(mapping.shopify_variant_id, MUG['variants']['nodes'][0]['id'])
        self.assertEqual(mapping.product_id.default_code, 'MUG-01')


@tagged('post_install', '-at_install')
class TestShopifyApiErrors(TransactionCase):
    """The real _graphql() with a mocked HTTP layer: every bad answer becomes a ShopifyError."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.instance = cls.env['shopify.instance'].create({
            'name': 'Error Store', 'shop_url': 'errors.myshopify.com', 'access_token': 'shpat_x'})

    def call(self, status, body=None, text=''):
        response = MagicMock(status_code=status, text=text or str(body))
        response.json.side_effect = (lambda: body) if body is not None else ValueError('no json')
        with patch('odoo.addons.shopify_sync.models.shopify_instance.requests.post', return_value=response):
            return self.instance._graphql('{ shop { name } }')

    def test_graphql_errors(self):
        self.assertEqual(self.call(200, {'data': {'shop': {'name': 'X'}}}), {'shop': {'name': 'X'}})
        for status, body, text, message in [
            (200, None, '<html>proxy error</html>', 'Invalid response'),
            (200, {'errors': 'Not Found'}, '', 'Not Found'),
            (200, {'errors': [{'message': 'Throttled'}]}, '', 'Throttled'),
            (200, ['unexpected'], '', 'Invalid response'),
            (429, {}, '', 'rate limit'),
            (500, None, 'boom', 'HTTP 500'),
        ]:
            with self.subTest(status=status, message=message), self.assertRaisesRegex(ShopifyError, message):
                self.call(status, body, text)
