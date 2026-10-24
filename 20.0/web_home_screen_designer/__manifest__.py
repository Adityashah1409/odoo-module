{
    'name': 'Home Screen Designer',
    'summary': 'App home screen for the backend: clock, greeting, app and menu search, app grid with a live '
               'designer (backgrounds, gradients, layout, icon style, app order and visibility), per user or company',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['web', 'base_setup'],
    'data': [
        'security/ir.access.csv',
        'data/home_screen_action.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'web_home_screen_designer/static/src/home_screen/**/*',
        ],
        'web.assets_tests': [
            'web_home_screen_designer/static/tests/tours/**/*',
        ],
    },
    'installable': True,
    'application': False,
}
