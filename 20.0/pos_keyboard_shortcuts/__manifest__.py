{
    'name': 'POS Keyboard Shortcuts',
    'summary': 'Run the Point of Sale from the keyboard: configurable shortcuts per POS and per screen '
               '(payment, numpad modes, search, payment methods, validate, new order, customer...) with a help sheet',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.access.csv',
        'views/pos_shortcut_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'pos_keyboard_shortcuts/static/src/app/**/*',
        ],
        'web.assets_tests': [
            'pos_keyboard_shortcuts/static/tests/tours/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
