from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests import TransactionCase

from ..models import queries

MODULE = 'odoo.addons.shopify_sync.models.shopify_instance.ShopifyInstance._graphql'


def money(amount):
    return {'shopMoney': {'amount': str(amount), 'currencyCode': 'USD'}}


ADDRESS = {'firstName': 'Ann', 'lastName': 'Lee', 'company': None, 'address1': '1 Main St', 'address2': None,
           'city': 'Austin', 'zip': '73301', 'provinceCode': 'TX', 'countryCodeV2': 'US', 'phone': '+1 555 0100'}

CUSTOMER = {'id': 'gid://shopify/Customer/1', 'firstName': 'Ann', 'lastName': 'Lee', 'email': 'ann@example.com',
            'phone': '+1 555 0100', 'defaultAddress': ADDRESS}

TSHIRT = {
    'id': 'gid://shopify/Product/10', 'title': 'Organic T-shirt', 'handle': 'organic-t-shirt', 'status': 'ACTIVE',
    'descriptionHtml': '<p>Soft</p>', 'vendor': 'Acme', 'productType': 'Apparel', 'tags': [],
    'options': [{'name': 'Size', 'optionValues': [{'name': 'S'}, {'name': 'M'}]}],
    'variants': {'nodes': [
        {'id': 'gid://shopify/ProductVariant/101', 'title': 'S', 'sku': 'TSHIRT-S', 'barcode': None, 'price': '25.00',
         'inventoryItem': {'id': 'gid://shopify/InventoryItem/1001'}, 'selectedOptions': [{'name': 'Size', 'value': 'S'}]},
        {'id': 'gid://shopify/ProductVariant/102', 'title': 'M', 'sku': 'TSHIRT-M', 'barcode': None, 'price': '25.00',
         'inventoryItem': {'id': 'gid://shopify/InventoryItem/1002'}, 'selectedOptions': [{'name': 'Size', 'value': 'M'}]},
    ]},
}

MUG = {
    'id': 'gid://shopify/Product/20', 'title': 'Coffee Mug', 'handle': 'coffee-mug', 'status': 'ACTIVE',
    'descriptionHtml': '', 'vendor': 'Acme', 'productType': '', 'tags': [],
    'options': [{'name': 'Title', 'optionValues': [{'name': 'Default Title'}]}],
    'variants': {'nodes': [
        {'id': 'gid://shopify/ProductVariant/201', 'title': 'Default Title', 'sku': 'MUG-01', 'barcode': None,
         'price': '12.00', 'inventoryItem': {'id': 'gid://shopify/InventoryItem/2001'},
         'selectedOptions': [{'name': 'Title', 'value': 'Default Title'}]},
    ]},
}


def make_order(number=1001, status='PAID', cancelled=False, sku='TSHIRT-S', variant='gid://shopify/ProductVariant/101'):
    return {
        'id': f'gid://shopify/Order/{number}', 'name': f'#{number}', 'createdAt': '2026-10-20T10:00:00Z',
        'cancelledAt': '2026-10-21T10:00:00Z' if cancelled else None,
        'email': 'ann@example.com', 'phone': None, 'currencyCode': 'USD', 'taxesIncluded': False, 'note': 'Gift wrap',
        'displayFinancialStatus': status, 'displayFulfillmentStatus': 'UNFULFILLED',
        'customer': CUSTOMER, 'shippingAddress': ADDRESS, 'billingAddress': ADDRESS,
        'totalDiscountsSet': money(5),
        'lineItems': {'nodes': [
            {'id': 'gid://shopify/LineItem/1', 'name': 'Organic T-shirt - S', 'sku': sku, 'quantity': 2,
             'variant': {'id': variant}, 'originalUnitPriceSet': money(25)},
        ]},
        'shippingLines': {'nodes': [{'title': 'Standard', 'originalPriceSet': money(7.5)}]},
    }


class FakeShopify:
    """Answers the connector's GraphQL calls from in-memory data and records mutations."""

    def __init__(self):
        self.products = [TSHIRT, MUG]
        self.customers = [CUSTOMER]
        self.orders = [make_order()]
        self.calls = []

    def __call__(self, instance, query, variables=None):
        variables = variables or {}
        self.calls.append((query, variables))
        page = {'hasNextPage': False, 'endCursor': None}
        if query == queries.SHOP:
            return {'shop': {'name': 'Demo Store', 'myshopifyDomain': 'demo.myshopify.com', 'currencyCode': 'USD'}}
        if query == queries.LOCATIONS:
            return {'locations': {'nodes': [{'id': 'gid://shopify/Location/1', 'name': 'Main warehouse', 'isActive': True}]}}
        if query == queries.PRODUCTS:
            return {'products': {'nodes': self.products, 'pageInfo': page}}
        if query == queries.CUSTOMERS:
            return {'customers': {'nodes': self.customers, 'pageInfo': page}}
        if query == queries.ORDERS:
            return {'orders': {'nodes': self.orders, 'pageInfo': page}}
        if query == queries.ORDER:
            return {'order': next(o for o in self.orders if o['id'] == variables['id'])}
        if query == queries.INVENTORY_SET:
            return {'inventorySetQuantities': {'userErrors': []}}
        if query == queries.FULFILLMENT_ORDERS:
            return {'order': {'fulfillmentOrders': {'nodes': [{'id': 'gid://shopify/FulfillmentOrder/9', 'status': 'OPEN'}]}}}
        if query == queries.FULFILLMENT_CREATE:
            return {'fulfillmentCreate': {'fulfillment': {'id': 'gid://shopify/Fulfillment/1', 'status': 'SUCCESS'},
                                          'userErrors': []}}
        if query == queries.PRODUCT_SET:
            product_input = variables['input']
            variants = [{'id': f'gid://shopify/ProductVariant/9{i}', 'title': '/'.join(o['name'] for o in v['optionValues']),
                         'sku': v.get('sku'), 'barcode': None, 'price': v['price'],
                         'inventoryItem': {'id': f'gid://shopify/InventoryItem/9{i}'},
                         'selectedOptions': [{'name': o['optionName'], 'value': o['name']} for o in v['optionValues']]}
                        for i, v in enumerate(product_input['variants'])]
            return {'productSet': {'product': {'id': product_input.get('id', 'gid://shopify/Product/99'),
                                               'title': product_input['title'], 'variants': {'nodes': variants}},
                                   'userErrors': []}}
        raise AssertionError(f"Unexpected query: {query[:80]}")

    def mutations(self, query):
        return [v for q, v in self.calls if q == query]


class ShopifyCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.currency_id = cls.env.ref('base.USD')
        cls.warehouse = cls.env['stock.warehouse'].search([('company_id', '=', cls.env.company.id)], limit=1)
        cls.instance = cls.env['shopify.instance'].create({
            'name': 'Demo Store', 'shop_url': 'demo.myshopify.com', 'access_token': 'shpat_test',
            'webhook_secret': 'whsec_test', 'warehouse_id': cls.warehouse.id,
        })

    def setUp(self):
        super().setUp()
        self.shopify = FakeShopify()
        fake = self.shopify
        patcher = patch(MODULE, autospec=True, side_effect=lambda inst, q, v=None: fake(inst, q, v))
        patcher.start()
        self.addCleanup(patcher.stop)

    @contextmanager
    def connected(self):
        self.instance.action_test_connection()
        yield self.instance
