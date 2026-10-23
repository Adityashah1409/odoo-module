"""GraphQL Admin API documents used by the connector."""

SHOP = "query { shop { name myshopifyDomain currencyCode } }"

LOCATIONS = """
query { locations(first: 100) { nodes { id name isActive } } }
"""

MONEY = "shopMoney { amount currencyCode }"

ADDRESS = "firstName lastName company address1 address2 city zip provinceCode countryCodeV2 phone"

PRODUCT_FIELDS = """
id title handle status descriptionHtml vendor productType tags
options { name optionValues { name } }
variants(first: 100) { nodes {
  id title sku barcode price
  inventoryItem { id }
  selectedOptions { name value }
} }
"""

PRODUCTS = """
query($cursor: String, $query: String) {
  products(first: 50, after: $cursor, query: $query) {
    nodes { %s }
    pageInfo { hasNextPage endCursor }
  }
}
""" % PRODUCT_FIELDS

CUSTOMER_FIELDS = """
id firstName lastName email phone
defaultAddress { %s }
""" % ADDRESS

CUSTOMERS = """
query($cursor: String, $query: String) {
  customers(first: 50, after: $cursor, query: $query) {
    nodes { %s }
    pageInfo { hasNextPage endCursor }
  }
}
""" % CUSTOMER_FIELDS

ORDER_FIELDS = """
id name createdAt cancelledAt email phone currencyCode taxesIncluded note
displayFinancialStatus displayFulfillmentStatus
customer { %(customer)s }
shippingAddress { %(address)s }
billingAddress { %(address)s }
totalDiscountsSet { %(money)s }
lineItems(first: 250) { nodes {
  id name sku quantity
  variant { id }
  originalUnitPriceSet { %(money)s }
} }
shippingLines(first: 10) { nodes { title originalPriceSet { %(money)s } } }
""" % {'customer': CUSTOMER_FIELDS, 'address': ADDRESS, 'money': MONEY}

ORDERS = """
query($cursor: String, $query: String) {
  orders(first: 25, after: $cursor, query: $query, sortKey: UPDATED_AT) {
    nodes { %s }
    pageInfo { hasNextPage endCursor }
  }
}
""" % ORDER_FIELDS

ORDER = """
query($id: ID!) { order(id: $id) { %s } }
""" % ORDER_FIELDS

FULFILLMENT_ORDERS = """
query($id: ID!) { order(id: $id) { fulfillmentOrders(first: 20) { nodes { id status } } } }
"""

FULFILLMENT_CREATE = """
mutation($fulfillment: FulfillmentInput!) {
  fulfillmentCreate(fulfillment: $fulfillment) {
    fulfillment { id status }
    userErrors { field message }
  }
}
"""

INVENTORY_SET = """
mutation($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) {
    userErrors { field message }
  }
}
"""

PRODUCT_SET = """
mutation($input: ProductSetInput!, $synchronous: Boolean!) {
  productSet(input: $input, synchronous: $synchronous) {
    product { %s }
    userErrors { field message }
  }
}
""" % PRODUCT_FIELDS
