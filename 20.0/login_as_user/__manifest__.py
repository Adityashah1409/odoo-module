{
    'name': 'Login As Other User',
    'summary': 'Let support administrators open Odoo as another user to see exactly what that user sees, with a '
               'reason, a banner, one-click switch back, rules on who can be impersonated and a full audit log',
    'version': '20.0.1.0.0',
    'category': 'Administration',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['base_setup', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/ir_config_parameter.xml',
        'data/ir_cron.xml',
        'views/login_as_log_views.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
        'views/frontend_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'login_as_user/static/src/login_as/**/*',
        ],
        'web.assets_frontend': [
            'login_as_user/static/src/frontend/**/*',
        ],
        'web.assets_tests': [
            'login_as_user/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
