{
    'name': 'E-mail Cc, Bcc and Reply-To',
    'summary': 'Cc and Bcc e-mail addresses and Reply-To in the e-mail composer, with company defaults and rules '
               'per document type, sender and sender group; logged in the chatter; Bcc really sent',
    'version': '19.0.1.0.0',
    'category': 'Productivity/Discuss',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/mail_cc_rule_views.xml',
        'views/res_config_settings_views.xml',
        'views/mail_mail_views.xml',
        'wizard/mail_compose_message_views.xml',
    ],
    'installable': True,
}
