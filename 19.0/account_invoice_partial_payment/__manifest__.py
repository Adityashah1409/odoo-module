{
    'name': 'Invoice Partial Payments',
    'summary': 'Allocate one customer receipt or vendor payment across several invoices or bills with partial '
               'amounts; the unallocated rest stays as outstanding credit. Batch history and checks.',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Accounting',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/sequence.xml',
        'views/account_partial_payment_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
}
