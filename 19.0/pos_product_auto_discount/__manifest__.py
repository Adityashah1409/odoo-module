{
    'name': 'POS Product Auto Discount',
    'summary': 'Automatic discounts in the Point of Sale: rules per product or POS category, minimum quantity, '
               'date range and happy hours, discount badges on product cards, report of discounts given',
    'version': '19.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/pos_auto_discount_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_product_auto_discount/static/src/app/**/*',
        ],
        'web.assets_tests': [
            'pos_product_auto_discount/static/tests/tours/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
