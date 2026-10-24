{
    'name': 'CPQ Product Configurator',
    'summary': 'Configure-Price-Quote: guided configuration of custom products on quotations '
               'with compatibility rules, live pricing and stock, and the BoM / manufacturing order generated for you',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'sale_stock', 'mrp'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence.xml',
        'views/cpq_configurator_views.xml',
        'views/cpq_configuration_views.xml',
        'views/sale_order_views.xml',
        'wizard/cpq_configure_wizard_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
