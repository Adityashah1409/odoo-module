{
    'name': 'Access Management',
    'summary': 'Restrict menus, models, fields, buttons, tabs, chatter, reports, actions, export and import per '
               'user or group, with record domains, read-only users, time windows, data masking, export '
               'tracking, PIN-protected menus, an access map and a dashboard',
    'version': '19.0.1.0.0',
    'category': 'Administration',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',
        'views/access_rule_views.xml',
        'views/access_menu_lock_views.xml',
        'views/access_export_log_views.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/access_map_views.xml',
        'wizard/access_rule_transfer_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'access_management/static/src/scss/access_management.scss',
            'access_management/static/src/js/**/*',
            'access_management/static/src/pin/**/*',
            'access_management/static/src/dashboard/**/*',
        ],
        'web.assets_tests': [
            'access_management/static/tests/tours/**/*',
        ],
    },
    'post_init_hook': '_post_init_hook',
    'application': True,
    'installable': True,
}
