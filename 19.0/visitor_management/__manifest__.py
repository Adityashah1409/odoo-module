{
    'name': 'Visitor Management',
    'summary': 'Register, check in and check out visitors: expected visits, invitations with a pass code, '
               'host notifications, self-service kiosk, printable visitor pass and reporting',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['hr', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/visitor_data.xml',
        'data/mail_template_data.xml',
        'report/visitor_pass_report.xml',
        'views/visitor_config_views.xml',
        'views/visitor_visit_views.xml',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'views/kiosk_templates.xml',
        'views/menus.xml',
    ],
    'demo': ['data/visitor_demo.xml'],
    'assets': {
        'web.assets_frontend': [
            'visitor_management/static/src/scss/kiosk.scss',
        ],
    },
    'installable': True,
    'application': True,
}
