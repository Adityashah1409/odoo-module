{
    'name': 'REST API Gateway',
    'summary': 'RESTful JSON API for Odoo: API keys, Basic auth and OAuth2 client credentials, CRUD, method calls, '
               'reports and files, custom endpoints, OpenAPI docs with a try-it page, request logs, rate limits, CORS',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['base_setup', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/rest_api_client_views.xml',
        'views/rest_api_endpoint_views.xml',
        'views/rest_api_log_views.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
        'views/docs_templates.xml',
    ],
    'installable': True,
    'application': True,
}
