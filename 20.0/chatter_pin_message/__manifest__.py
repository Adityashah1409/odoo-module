{
    'name': 'Chatter: Pin Messages',
    'summary': 'Rules for pinned chatter messages (who can pin, how many, which messages), who pinned '
               'each message and an overview of all pinned messages',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Discuss',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'data': [
        'views/mail_message_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
}
