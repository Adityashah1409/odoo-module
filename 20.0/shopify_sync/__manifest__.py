{
    'name': 'Shopify Sync',
    'summary': 'Shopify connector: products, customers, orders, stock levels, '
               'fulfillments and webhooks, with a sync queue and logs',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'sale_stock'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/shopify_instance_views.xml',
        'views/shopify_mapping_views.xml',
        'views/shopify_queue_views.xml',
        'views/sale_order_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
}
