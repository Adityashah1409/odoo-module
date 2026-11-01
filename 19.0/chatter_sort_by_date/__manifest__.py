{
    'name': 'Chatter: Sort by Date',
    'summary': 'Read the chatter oldest first or newest first: a toggle in the chatter, remembered per user, '
               'with a company default; oldest first starts from the very first message',
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
            'chatter_sort_by_date/static/src/**/*',
        ],
        'web.assets_tests': [
            'chatter_sort_by_date/static/tests/tours/*.js',
        ],
    },
    'installable': True,
}
