{
    'name': 'WhatsApp (Whapi.Cloud)',
    'summary': 'Chat with customers on WhatsApp from Odoo through Whapi.Cloud: live inbox, groups, media, '
               'replies, forwards, delivery and read ticks, templates and "Send by WhatsApp" on any document',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Discuss',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/whapi_account_views.xml',
        'views/whapi_chat_views.xml',
        'views/whapi_message_views.xml',
        'views/whapi_template_views.xml',
        'wizard/whapi_composer_views.xml',
        'views/res_partner_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'whatsapp_whapi/static/src/**/*',
        ],
        'web.assets_tests': [
            'whatsapp_whapi/static/tests/tours/**/*',
        ],
    },
    'application': True,
    'installable': True,
}
