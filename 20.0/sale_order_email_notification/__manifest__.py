{
    'name': 'Sales Order E-mail Notifications',
    'summary': 'Notification rules for new quotations, confirmed and cancelled orders: who gets an e-mail '
               '(users, addresses, salesperson, team leader, customer), for which teams, channels and amounts',
    'version': '20.0.1.0.0',
    'category': 'Sales/Sales',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['sale'],
    'data': [
        'security/ir.access.csv',
        'data/mail_template_data.xml',
        'data/notification_rule_data.xml',
        'views/sale_order_notification_rule_views.xml',
    ],
    'installable': True,
}
