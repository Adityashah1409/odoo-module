{
    'name': 'Power BI Connector',
    'summary': 'Send Odoo data to Power BI: push datasets through the Power BI REST API, or a secured '
               'JSON feed for Power BI Desktop / Service, plus Power BI reports embedded in Odoo',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['base', 'web'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/powerbi_connection_views.xml',
        'views/powerbi_dataset_views.xml',
        'views/powerbi_report_views.xml',
        'views/powerbi_log_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
}
