{
    'name': 'Activity Management',
    'summary': 'Activity dashboard, history of done and cancelled activities, cancel with reason, feedback, '
               'supervisors, tags and priority, mass scheduling for several users/records, recurring activities, '
               'time tracking and reminder digests',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Discuss',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['mail', 'base_setup'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/mail_activity_tag_views.xml',
        'views/mail_activity_views.xml',
        'views/res_users_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/activity_wizard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'activity_management/static/src/dashboard/**/*',
        ],
        'web.assets_tests': [
            'activity_management/static/tests/tours/**/*',
        ],
    },
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'application': True,
}
