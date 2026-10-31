{
    'name': 'Short URLs & QR Codes',
    'summary': 'Short links with QR codes for your website pages and any URL: custom or generated codes, expiry, '
               'marketing channels and UTM tags, click statistics, automatic rules, page dialog and snippets',
    'version': '19.0.1.0.0',
    'category': 'Website/Website',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['website', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/short_url_data.xml',
        'views/short_url_views.xml',
        'views/short_url_click_views.xml',
        'views/short_url_rule_views.xml',
        'views/res_config_settings_views.xml',
        'views/templates.xml',
        'views/snippets.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'short_urls/static/src/backend/**/*',
        ],
        'web.assets_frontend': [
            'short_urls/static/src/snippets/**/*',
        ],
        'web.assets_tests': [
            'short_urls/static/tests/tours/**/*',
        ],
    },
    'installable': True,
}
