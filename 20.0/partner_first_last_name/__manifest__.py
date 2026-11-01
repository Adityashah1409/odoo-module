{
    'name': 'Contact First, Middle and Last Name',
    'summary': 'Separate first, middle and last name on contacts, users, CRM leads and the sign-up form, with the '
               'display order of your choice (John Smith / Smith John / Smith, John) and automatic splitting',
    'version': '20.0.1.0.0',
    'category': 'Sales/CRM',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['contacts', 'crm', 'auth_signup'],
    'data': [
        'data/ir_config_parameter.xml',
        'views/res_partner_views.xml',
        'views/res_users_views.xml',
        'views/crm_lead_views.xml',
        'views/res_config_settings_views.xml',
        'views/auth_signup_templates.xml',
    ],
    'assets': {
        'web.assets_tests': [
            'partner_first_last_name/static/tests/tours/**/*',
        ],
    },
    'post_init_hook': '_post_init_split_names',
    'installable': True,
}
