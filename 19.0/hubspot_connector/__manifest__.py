{
    'name': 'HubSpot Connector',
    'summary': 'Two-way HubSpot sync: companies, contacts, deals, products, quotes, invoices, notes, tasks, '
               'meetings and e-mails, with queue, retries, webhooks, owner/stage/field mapping and a dashboard',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['crm', 'sale', 'calendar'],
    'external_dependencies': {'python': ['requests']},
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/hubspot_queue_views.xml',
        'views/hubspot_account_views.xml',
        'views/hubspot_linked_views.xml',
        'wizard/hubspot_export_wizard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hubspot_connector/static/src/dashboard/**/*',
        ],
        'web.assets_tests': [
            'hubspot_connector/static/tests/tours/**/*',
        ],
    },
    'installable': True,
    'application': True,
}
