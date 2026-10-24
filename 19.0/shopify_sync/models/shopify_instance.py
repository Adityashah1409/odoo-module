import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from . import queries

_logger = logging.getLogger(__name__)

TIMEOUT = 40
FINANCIAL_STATUSES = [
    ('PENDING', 'Pending'), ('AUTHORIZED', 'Authorized'), ('PARTIALLY_PAID', 'Partially paid'),
    ('PAID', 'Paid'), ('PARTIALLY_REFUNDED', 'Partially refunded'), ('REFUNDED', 'Refunded'),
    ('VOIDED', 'Voided'), ('EXPIRED', 'Expired'),
]


class ShopifyError(Exception):
    """Raised for API errors; the message ends up on the queue line / log."""


def gid(kind, value):
    """Numeric id (webhooks, REST) -> GraphQL global id."""
    value = str(value)
    return value if value.startswith('gid://') else f'gid://shopify/{kind}/{value}'


class ShopifyInstance(models.Model):
    _name = 'shopify.instance'
    _description = 'Shopify Store'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer()
    state = fields.Selection([('draft', 'Not connected'), ('connected', 'Connected'), ('error', 'Error')],
                             default='draft', required=True, readonly=True, copy=False)
    shop_url = fields.Char("Shop domain", required=True, help="e.g. my-store.myshopify.com")
    access_token = fields.Char("Admin API access token", groups='shopify_sync.group_shopify_manager',
                               help="From a custom app (Settings › Apps › Develop apps) with read/write "
                                    "access to products, customers, orders, inventory and fulfillments.")
    webhook_secret = fields.Char("Webhook signing secret", groups='shopify_sync.group_shopify_manager',
                                 help="The app's API secret key, used to verify webhook signatures.")
    api_version = fields.Char(default='2025-10', required=True)
    shop_currency = fields.Char(readonly=True)

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    warehouse_id = fields.Many2one('stock.warehouse', required=True, check_company=True,
                                   default=lambda self: self.env['stock.warehouse'].search(
                                       [('company_id', '=', self.env.company.id)], limit=1))
    pricelist_id = fields.Many2one('product.pricelist', check_company=True)
    team_id = fields.Many2one('crm.team', string="Sales team")
    user_id = fields.Many2one('res.users', string="Salesperson")
    shipping_product_id = fields.Many2one('product.product', domain=[('type', '=', 'service')])
    discount_product_id = fields.Many2one('product.product', domain=[('type', '=', 'service')])

    # order workflow
    import_financial_statuses = fields.Char(
        default='PAID,PARTIALLY_PAID,AUTHORIZED', required=True,
        help="Comma separated Shopify financial statuses to import: " + ', '.join(k for k, _v in FINANCIAL_STATUSES))
    auto_confirm_order = fields.Boolean(default=True)
    auto_create_invoice = fields.Boolean(help="Create and post the invoice of paid orders.")
    create_missing_products = fields.Boolean(
        default=True, help="Create products for Shopify variants that match no mapping and no internal reference.")
    order_import_from = fields.Datetime(help="Next import only fetches orders updated after this date.")
    product_import_from = fields.Datetime()
    customer_import_from = fields.Datetime()

    # automation
    auto_import_orders = fields.Boolean(default=True)
    auto_export_stock = fields.Boolean(default=True)
    stock_field = fields.Selection([('free_qty', 'Free to use'), ('qty_available', 'On hand'),
                                    ('virtual_available', 'Forecasted')], default='free_qty', required=True)
    webhook_url = fields.Char(compute='_compute_webhook_url')

    location_ids = fields.One2many('shopify.location', 'instance_id')
    product_map_ids = fields.One2many('shopify.product.map', 'instance_id')
    order_ids = fields.One2many('sale.order', 'shopify_instance_id')
    order_count = fields.Integer(compute='_compute_counts')
    product_count = fields.Integer(compute='_compute_counts')
    customer_count = fields.Integer(compute='_compute_counts')
    failed_queue_count = fields.Integer(compute='_compute_counts')
    pending_queue_count = fields.Integer(compute='_compute_counts')
    orders_to_ship_count = fields.Integer(compute='_compute_counts')

    _shop_uniq = models.Constraint('UNIQUE(shop_url, company_id)', "This store is already connected for this company.")

    def _compute_webhook_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for instance in self:
            instance.webhook_url = f"{base}/shopify_sync/webhook/{instance.id or 0}"

    def _compute_counts(self):
        def counts(model, domain):
            return dict(self.env[model].sudo()._read_group(
                [('instance_id' if model != 'sale.order' else 'shopify_instance_id', 'in', self.ids)] + domain,
                ['instance_id' if model != 'sale.order' else 'shopify_instance_id'], ['__count']))
        orders = counts('sale.order', [])
        to_ship = counts('sale.order', [('delivery_status', 'in', ('pending', 'partial')), ('state', '=', 'sale')])
        products = counts('shopify.product.map', [])
        customers = counts('shopify.customer.map', [])
        failed = counts('shopify.queue', [('state', '=', 'failed')])
        pending = counts('shopify.queue', [('state', '=', 'draft')])
        for instance in self:
            instance.order_count = orders.get(instance, 0)
            instance.orders_to_ship_count = to_ship.get(instance, 0)
            instance.product_count = products.get(instance, 0)
            instance.customer_count = customers.get(instance, 0)
            instance.failed_queue_count = failed.get(instance, 0)
            instance.pending_queue_count = pending.get(instance, 0)

    @api.onchange('shop_url')
    def _onchange_shop_url(self):
        if self.shop_url:
            self.shop_url = self.shop_url.replace('https://', '').replace('http://', '').strip('/')

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------
    def _graphql(self, query, variables=None):
        """Run a GraphQL Admin API call and return its `data`."""
        self.ensure_one()
        instance = self.sudo()
        url = f"https://{instance.shop_url}/admin/api/{instance.api_version}/graphql.json"
        try:
            response = requests.post(url, json={'query': query, 'variables': variables or {}}, timeout=TIMEOUT,
                                     headers={'X-Shopify-Access-Token': instance.access_token or '',
                                              'Content-Type': 'application/json'})
        except requests.RequestException as e:
            raise ShopifyError(str(e)) from e
        if response.status_code == 429:
            raise ShopifyError("Shopify rate limit reached, will retry.")
        if response.status_code >= 400:
            raise ShopifyError(f"HTTP {response.status_code}: {response.text[:300]}")
        try:
            payload = response.json()
        except ValueError:
            raise ShopifyError(f"Invalid response from Shopify (HTTP {response.status_code}): "
                               f"{response.text[:200]}") from None
        if not isinstance(payload, dict):
            raise ShopifyError("Invalid response from Shopify.")
        errors = payload.get('errors')
        if errors:
            if isinstance(errors, str):
                raise ShopifyError(errors)
            raise ShopifyError('; '.join(e.get('message', str(e)) if isinstance(e, dict) else str(e)
                                         for e in errors))
        return payload.get('data') or {}

    def _paginate(self, query, root, search=None, limit_pages=40):
        """Yield nodes of a paginated connection."""
        cursor = None
        for _page in range(limit_pages):
            data = self._graphql(query, {'cursor': cursor, 'query': search})[root]
            yield from data['nodes']
            if not data['pageInfo']['hasNextPage']:
                break
            cursor = data['pageInfo']['endCursor']

    @staticmethod
    def _user_errors(result, operation):
        errors = result.get('userErrors') or []
        if errors:
            raise ShopifyError(f"{operation}: " + '; '.join(e['message'] for e in errors))

    def _log(self, operation, message, level='info', res_model=False, res_id=False):
        self.env['shopify.log'].sudo().create({
            'instance_id': self.id, 'operation': operation, 'message': message, 'level': level,
            'res_model': res_model, 'res_id': res_id,
        })

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------
    def action_test_connection(self):
        self.ensure_one()
        try:
            shop = self._graphql(queries.SHOP)['shop']
        except ShopifyError as e:
            self.state = 'error'
            self._log('connection', str(e), level='error')
            raise UserError(_("Could not connect to %(shop)s:\n%(error)s", shop=self.shop_url, error=e))
        self.write({'state': 'connected', 'shop_currency': shop.get('currencyCode')})
        self._log('connection', _("Connected to %s", shop.get('name')))
        self.action_import_locations()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'type': 'success', 'message': _("Connected to %s", shop.get('name'))}}

    def action_import_locations(self):
        for instance in self:
            nodes = instance._graphql(queries.LOCATIONS)['locations']['nodes']
            existing = {loc.shopify_id: loc for loc in instance.location_ids}
            for node in nodes:
                values = {'name': node['name'], 'active': node.get('isActive', True)}
                if node['id'] in existing:
                    existing[node['id']].write(values)
                else:
                    self.env['shopify.location'].create(dict(values, instance_id=instance.id, shopify_id=node['id'],
                                                             warehouse_id=instance.warehouse_id.id))
        return True

    def action_import_products(self):
        return self._import('product', queries.PRODUCTS, 'products', 'product_import_from')

    def action_import_customers(self):
        return self._import('customer', queries.CUSTOMERS, 'customers', 'customer_import_from')

    def action_import_orders(self):
        return self._import('order', queries.ORDERS, 'orders', 'order_import_from')

    def _import(self, data_type, query, root, date_field):
        """Fetch records updated since the last import into the queue, then process the queue."""
        Queue = self.env['shopify.queue']
        for instance in self:
            started = fields.Datetime.now()
            since = instance[date_field]
            search = f"updated_at:>'{since.isoformat()}Z'" if since else None
            try:
                count = 0
                for node in instance._paginate(query, root, search):
                    Queue._add(instance, data_type, node)
                    count += 1
            except ShopifyError as e:
                instance._log(f'import_{data_type}', str(e), level='error')
                continue
            instance[date_field] = started
            instance._log(f'import_{data_type}', _("%(count)s %(type)s(s) fetched.", count=count, type=data_type))
        Queue.search([('instance_id', 'in', self.ids), ('state', '=', 'draft')])._process()
        return True

    def action_export_stock(self):
        for instance in self:
            instance._export_stock()
        return True

    def action_view_orders(self):
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_orders')
        action['domain'] = [('shopify_instance_id', '=', self.id)]
        action['context'] = {}
        return action

    def action_view_products(self):
        return self._open('shopify_sync.action_shopify_product_map')

    def action_view_customers(self):
        return self._open('shopify_sync.action_shopify_customer_map')

    def action_view_queue(self):
        action = self._open('shopify_sync.action_shopify_queue')
        action['context'] = {'search_default_failed': 1, 'search_default_draft': 1}
        return action

    def _open(self, xmlid):
        action = self.env['ir.actions.act_window']._for_xml_id(xmlid)
        action['domain'] = [('instance_id', '=', self.id)]
        return action

    # ------------------------------------------------------------------
    # Import: products
    # ------------------------------------------------------------------
    def _import_product(self, data):
        """Create or update the Odoo products of one Shopify product (with its variants)."""
        self.ensure_one()
        Map = self.env['shopify.product.map']
        Product = self.env['product.product']
        variants = data['variants']['nodes']
        maps = Map.search([('instance_id', '=', self.id), ('shopify_variant_id', 'in', [v['id'] for v in variants])])
        by_variant = {m.shopify_variant_id: m for m in maps}
        unmatched = []
        for variant in variants:
            product = by_variant.get(variant['id'], Map).product_id
            if not product and variant.get('sku'):
                product = Product.search([('default_code', '=', variant['sku'])], limit=1)
            if not product and variant.get('barcode'):
                product = Product.search([('barcode', '=', variant['barcode'])], limit=1)
            if product:
                self._map_variant(data, variant, product)
            else:
                unmatched.append(variant)
        if unmatched:
            if not self.create_missing_products:
                raise ShopifyError(_("No Odoo product for SKU(s) %s", ', '.join(v.get('sku') or v['id'] for v in unmatched)))
            template = self._create_template(data, unmatched)
            for variant in unmatched:
                self._map_variant(data, variant, self._match_template_variant(template, variant))
        return Map.search([('instance_id', '=', self.id), ('shopify_product_id', '=', data['id'])])

    def _map_variant(self, data, variant, product):
        Map = self.env['shopify.product.map']
        values = {
            'instance_id': self.id, 'product_id': product.id,
            'shopify_product_id': data['id'], 'shopify_variant_id': variant['id'],
            'inventory_item_id': (variant.get('inventoryItem') or {}).get('id'),
            'sku': variant.get('sku'), 'title': data['title'] + (
                f" - {variant['title']}" if variant.get('title') not in (None, 'Default Title') else ''),
            'last_sync': fields.Datetime.now(),
        }
        existing = Map.search([('instance_id', '=', self.id), ('shopify_variant_id', '=', variant['id'])], limit=1)
        if existing:
            existing.write(values)
        else:
            Map.create(values)
        if variant.get('sku') and not product.default_code:
            product.default_code = variant['sku']

    def _real_options(self, data):
        return [o for o in data.get('options') or []
                if not (o['name'] == 'Title' and [v['name'] for v in o['optionValues']] == ['Default Title'])]

    def _create_template(self, data, variants):
        Attribute = self.env['product.attribute']
        lines = []
        for option in self._real_options(data):
            attribute = Attribute.search([('name', '=', option['name'])], limit=1) or \
                Attribute.create({'name': option['name'], 'create_variant': 'always'})
            values = self.env['product.attribute.value']
            for value in option['optionValues']:
                values |= attribute.value_ids.filtered(lambda v, n=value['name']: v.name == n) or \
                    self.env['product.attribute.value'].create({'attribute_id': attribute.id, 'name': value['name']})
            lines.append((0, 0, {'attribute_id': attribute.id, 'value_ids': [(6, 0, values.ids)]}))
        first = variants[0]
        template = self.env['product.template'].create({
            'name': data['title'],
            'type': 'consu',
            'is_storable': True,
            'list_price': float(first.get('price') or 0.0),
            'description_sale': False,
            'attribute_line_ids': lines,
            'company_id': False,
        })
        if len(template.product_variant_ids) == 1 and first.get('sku'):
            template.product_variant_ids.write({'default_code': first['sku'], 'barcode': first.get('barcode') or False})
        self._log('import_product', _("Created product %s", template.display_name),
                  res_model='product.template', res_id=template.id)
        return template

    def _match_template_variant(self, template, variant):
        wanted = {(o['name'], o['value']) for o in variant.get('selectedOptions') or [] if o['name'] != 'Title'}
        for product in template.product_variant_ids:
            values = {(v.attribute_id.name, v.name) for v in product.product_template_attribute_value_ids}
            if values == wanted or (not wanted and not values):
                if variant.get('sku') and not product.default_code:
                    product.default_code = variant['sku']
                return product
        raise ShopifyError(_("Variant %s could not be matched to a product variant.", variant.get('title')))

    def _product_for_line(self, line):
        """Odoo product for an order line (mapping, then SKU, then auto-create)."""
        variant_id = (line.get('variant') or {}).get('id')
        if variant_id:
            mapping = self.env['shopify.product.map'].search(
                [('instance_id', '=', self.id), ('shopify_variant_id', '=', variant_id)], limit=1)
            if mapping:
                return mapping.product_id
        if line.get('sku'):
            product = self.env['product.product'].search([('default_code', '=', line['sku'])], limit=1)
            if product:
                return product
        if not self.create_missing_products:
            raise ShopifyError(_("No product for order line %(name)s (SKU %(sku)s).",
                                 name=line.get('name'), sku=line.get('sku') or '-'))
        return self.env['product.product'].create({
            'name': line.get('name') or line.get('sku'), 'default_code': line.get('sku') or False,
            'type': 'consu', 'is_storable': True,
            'list_price': float(line['originalUnitPriceSet']['shopMoney']['amount']),
        })

    # ------------------------------------------------------------------
    # Import: customers
    # ------------------------------------------------------------------
    def _address_values(self, address):
        if not address:
            return {}
        country = self.env['res.country'].search([('code', '=', address.get('countryCodeV2'))], limit=1)
        state = country and address.get('provinceCode') and self.env['res.country.state'].search(
            [('country_id', '=', country.id), ('code', '=', address['provinceCode'])], limit=1)
        name = ' '.join(filter(None, [address.get('firstName'), address.get('lastName')]))
        return {
            'name': name or address.get('company') or False,
            'street': address.get('address1') or False, 'street2': address.get('address2') or False,
            'city': address.get('city') or False, 'zip': address.get('zip') or False,
            'country_id': country.id or False, 'state_id': state.id if state else False,
            'phone': address.get('phone') or False,
        }

    def _import_customer(self, data):
        self.ensure_one()
        Map = self.env['shopify.customer.map']
        Partner = self.env['res.partner']
        mapping = Map.search([('instance_id', '=', self.id), ('shopify_customer_id', '=', data['id'])], limit=1)
        partner = mapping.partner_id
        if not partner and data.get('email'):
            partner = Partner.search([('email', '=ilike', data['email']), ('parent_id', '=', False)], limit=1)
        values = {k: v for k, v in self._address_values(data.get('defaultAddress')).items() if v}
        name = ' '.join(filter(None, [data.get('firstName'), data.get('lastName')]))
        values.update({'name': name or values.get('name') or data.get('email') or _("Shopify customer"),
                       'email': data.get('email') or False})
        if data.get('phone'):
            values['phone'] = data['phone']
        if partner:
            partner.write({k: v for k, v in values.items() if v})
        else:
            partner = Partner.create(dict(values, customer_rank=1))
        if not mapping:
            Map.create({'instance_id': self.id, 'partner_id': partner.id, 'shopify_customer_id': data['id']})
        return partner

    def _child_address(self, partner, address, kind):
        values = self._address_values(address)
        if not values or not values.get('street'):
            return partner
        fields_to_compare = ('street', 'city', 'zip', 'country_id')
        if all((partner[f].id if f == 'country_id' else partner[f]) == values[f] for f in fields_to_compare):
            return partner
        existing = partner.child_ids.filtered(
            lambda c: c.type == kind and all((c[f].id if f == 'country_id' else c[f]) == values[f]
                                             for f in fields_to_compare))
        return existing[:1] or self.env['res.partner'].create(dict(values, parent_id=partner.id, type=kind))

    # ------------------------------------------------------------------
    # Import: orders
    # ------------------------------------------------------------------
    def _allowed_statuses(self):
        return {s.strip().upper() for s in (self.import_financial_statuses or '').split(',') if s.strip()}

    def _import_order(self, data):
        """Create (or update the status of) the sale order of a Shopify order. Returns the order or False."""
        self.ensure_one()
        SaleOrder = self.env['sale.order']
        order = SaleOrder.search([('shopify_instance_id', '=', self.id), ('shopify_order_id', '=', data['id'])], limit=1)
        if order:
            order._shopify_update_status(data)
            return order
        if data.get('cancelledAt'):
            return False
        if data.get('displayFinancialStatus') not in self._allowed_statuses():
            return False
        pricelist = self.pricelist_id
        if pricelist and data.get('currencyCode') and pricelist.currency_id.name != data['currencyCode']:
            raise ShopifyError(_("Order currency %(order)s differs from pricelist currency %(pricelist)s.",
                                 order=data['currencyCode'], pricelist=pricelist.currency_id.name))
        customer = data.get('customer')
        if customer:
            partner = self._import_customer(customer)
        else:
            partner = self.env['res.partner'].create(dict(
                {k: v for k, v in self._address_values(data.get('billingAddress') or data.get('shippingAddress')).items() if v},
                email=data.get('email') or False))
            if not partner.name:
                partner.name = data.get('email') or data['name']
        lines = []
        for line in data['lineItems']['nodes']:
            if not line.get('quantity'):
                continue
            product = self._product_for_line(line)
            lines.append((0, 0, {
                'product_id': product.id, 'name': line.get('name') or product.display_name,
                'product_uom_qty': line['quantity'],
                'price_unit': float(line['originalUnitPriceSet']['shopMoney']['amount']),
            }))
        for shipping in data.get('shippingLines', {}).get('nodes', []):
            amount = float(shipping['originalPriceSet']['shopMoney']['amount'])
            if amount:
                product = self.shipping_product_id or self._service_product('shopify_shipping', _("Shopify shipping"))
                lines.append((0, 0, {'product_id': product.id, 'name': shipping.get('title') or product.name,
                                     'product_uom_qty': 1, 'price_unit': amount}))
        discount = float((data.get('totalDiscountsSet') or {}).get('shopMoney', {}).get('amount') or 0)
        if discount:
            product = self.discount_product_id or self._service_product('shopify_discount', _("Shopify discount"))
            lines.append((0, 0, {'product_id': product.id, 'name': _("Discount"),
                                 'product_uom_qty': 1, 'price_unit': -discount}))
        values = {
            'partner_id': partner.id,
            'partner_invoice_id': self._child_address(partner, data.get('billingAddress'), 'invoice').id,
            'partner_shipping_id': self._child_address(partner, data.get('shippingAddress'), 'delivery').id,
            'company_id': self.company_id.id,
            'warehouse_id': self.warehouse_id.id,
            'client_order_ref': data['name'],
            'origin': f"Shopify {data['name']}",
            'note': data.get('note') or False,
            'order_line': lines,
            'shopify_instance_id': self.id,
            'shopify_order_id': data['id'],
            'shopify_order_name': data['name'],
            'shopify_financial_status': data.get('displayFinancialStatus'),
            'shopify_fulfillment_status': data.get('displayFulfillmentStatus'),
        }
        if pricelist:
            values['pricelist_id'] = pricelist.id
        if self.team_id:
            values['team_id'] = self.team_id.id
        if self.user_id:
            values['user_id'] = self.user_id.id
        order = SaleOrder.with_company(self.company_id).create(values)
        # keep Shopify prices even if the pricelist would compute others
        for line, (_cmd, _id, vals) in zip(order.order_line, lines):
            if line.price_unit != vals['price_unit']:
                line.price_unit = vals['price_unit']
        if self.auto_confirm_order:
            order.action_confirm()
            if self.auto_create_invoice and data.get('displayFinancialStatus') == 'PAID':
                invoice = order._create_invoices()
                invoice.action_post()
        self._log('import_order', _("Order %(name)s imported as %(order)s", name=data['name'], order=order.name),
                  res_model='sale.order', res_id=order.id)
        return order

    def _service_product(self, xml_name, name):
        imd = self.env['ir.model.data']
        product = self.env.ref(f'shopify_sync.{xml_name}', raise_if_not_found=False)
        if not product:
            product = self.env['product.product'].create({'name': name, 'type': 'service', 'invoice_policy': 'order'})
            imd.create({'module': 'shopify_sync', 'name': xml_name, 'model': 'product.product',
                        'res_id': product.id, 'noupdate': True})
        return product

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def _export_stock(self):
        """Push stock levels of mapped variants to each mapped Shopify location."""
        self.ensure_one()
        maps = self.product_map_ids.filtered(lambda m: m.inventory_item_id and m.product_id.is_storable)
        locations = self.location_ids.filtered(lambda loc: loc.active and loc.warehouse_id and loc.export_stock)
        if not maps or not locations:
            return 0
        quantities = []
        for location in locations:
            products = maps.product_id.with_context(warehouse_id=location.warehouse_id.id)
            for mapping in maps:
                product = products.browse(mapping.product_id.id)
                quantities.append({
                    'inventoryItemId': mapping.inventory_item_id,
                    'locationId': location.shopify_id,
                    'quantity': max(int(product[self.stock_field]), 0),
                })
        for start in range(0, len(quantities), 250):
            result = self._graphql(queries.INVENTORY_SET, {'input': {
                'name': 'available', 'reason': 'correction', 'ignoreCompareQuantity': True,
                'quantities': quantities[start:start + 250],
            }})['inventorySetQuantities']
            self._user_errors(result, 'inventorySetQuantities')
        self._log('export_stock', _("Stock exported for %(count)s variant(s) on %(loc)s location(s).",
                                    count=len(maps), loc=len(locations)))
        return len(quantities)

    def _export_product(self, template):
        """Create or update a product (and its variants) in Shopify from an Odoo template."""
        self.ensure_one()
        options = [{'name': line.attribute_id.name, 'values': [{'name': v.name} for v in line.value_ids]}
                   for line in template.attribute_line_ids if line.attribute_id.create_variant == 'always']
        variants = []
        for product in template.product_variant_ids:
            option_values = [{'optionName': v.attribute_id.name, 'name': v.name}
                             for v in product.product_template_attribute_value_ids]
            variants.append({
                'optionValues': option_values or [{'optionName': 'Title', 'name': 'Default Title'}],
                'price': f"{product.lst_price:.2f}",
                'sku': product.default_code or None,
                'barcode': product.barcode or None,
            })
        mapping = self.product_map_ids.filtered(lambda m: m.product_id.product_tmpl_id == template)[:1]
        product_input = {
            'title': template.name,
            'descriptionHtml': str(template.description_sale or ''),
            'status': 'ACTIVE' if template.sale_ok and template.active else 'DRAFT',
            'productOptions': options or [{'name': 'Title', 'values': [{'name': 'Default Title'}]}],
            'variants': variants,
        }
        if mapping:
            product_input['id'] = mapping.shopify_product_id
        result = self._graphql(queries.PRODUCT_SET, {'input': product_input, 'synchronous': True})['productSet']
        self._user_errors(result, 'productSet')
        data = result['product']
        for variant in data['variants']['nodes']:
            product = self._match_template_variant(template, variant)
            self._map_variant(data, variant, product)
        self._log('export_product', _("Product %s exported.", template.display_name),
                  res_model='product.template', res_id=template.id)
        return data['id']

    # ------------------------------------------------------------------
    # Crons
    # ------------------------------------------------------------------
    @api.model
    def _cron_import_orders(self):
        self.search([('state', '=', 'connected'), ('auto_import_orders', '=', True)]).action_import_orders()

    @api.model
    def _cron_export_stock(self):
        for instance in self.search([('state', '=', 'connected'), ('auto_export_stock', '=', True)]):
            try:
                instance._export_stock()
            except ShopifyError as e:
                instance._log('export_stock', str(e), level='error')
