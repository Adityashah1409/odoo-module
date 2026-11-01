{
    'name': 'Chatter: Pin Messages',
    'summary': 'Pin important messages and notes in the chatter of any record: pinned bar on top of the '
               'chatter, jump to the message, who pinned it, access rules, limit and an overview of all pins',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Discuss',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'data': [
        'views/mail_message_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'chatter_pin_message/static/src/**/*',
        ],
        'web.assets_tests': [
            'chatter_pin_message/static/tests/tours/*.js',
        ],
    },
    'installable': True,
}
