{
    'name': 'Cash on Delivery: OTP and Collections',
    'summary': 'Cash on Delivery for the eShop with a delivery code (OTP) for the customer, collection receipts '
               'for the driver, cash deposit with automatic invoice and payment, and availability rules',
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['website_sale', 'delivery', 'account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/cod_data.xml',
        'data/mail_template_data.xml',
        'report/cod_collection_report.xml',
        'views/payment_provider_views.xml',
        'views/sale_cod_collection_views.xml',
        'views/sale_order_views.xml',
        'views/templates.xml',
        'wizard/cod_wizard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_tests': [
            'website_sale_cod/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
