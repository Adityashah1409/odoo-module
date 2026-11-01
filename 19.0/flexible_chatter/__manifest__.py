{
    'name': 'Flexible Chatter',
    'summary': 'Choose where the chatter goes (automatic, on the side, below the form), drag its width, hide it '
               'when you need room; remembered per user with company defaults',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Discuss',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'data': [
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'flexible_chatter/static/src/**/*',
        ],
        'web.assets_tests': [
            'flexible_chatter/static/tests/tours/*.js',
        ],
    },
    'installable': True,
}
