{
    'name': 'Warehouse Average Costing',
    'summary': 'Average cost per warehouse: receipts, deliveries and inter-warehouse transfers valued at each '
               'warehouse\'s own average cost, cost history, approval-based cost adjustments, valuation reports '
               '(screen, Excel, PDF), cost matrix import/export and a dashboard',
    'version': '20.0.1.0.0',
    'category': 'Inventory/Inventory',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['stock_account'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/stock_warehouse_cost_views.xml',
        'views/stock_warehouse_cost_adjustment_views.xml',
        'views/product_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/stock_warehouse_valuation_report_views.xml',
        'wizard/stock_warehouse_cost_matrix_views.xml',
        'report/warehouse_valuation_report.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'warehouse_avg_costing/static/src/dashboard/**/*',
        ],
        'web.assets_tests': [
            'warehouse_avg_costing/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
