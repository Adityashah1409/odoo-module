{
    'name': 'Import Bills of Materials',
    'summary': 'Import Bills of Materials (components, quantities, units, operations) '
               'from CSV or Excel, with product matching, update modes and a row-level error report',
    'version': '19.0.1.0.0',
    'category': 'Supply Chain/Manufacturing',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['mrp'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/mrp_bom_import_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
