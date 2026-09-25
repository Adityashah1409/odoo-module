{
    'name': 'Backend Theme',
    'version': '20.0.1.0.0',
    'category': 'Themes/Backend',
    'summary': 'Configurable colors, typography and UI scale for the Odoo backend',
    'description': """
Configurable backend theme for the Odoo 20 web client.

Phase 1 provides the foundation every later feature builds on: global theme
settings, per-user preferences, a central theme plugin in the web client and
CSS-variable based styling.
""",
    'author': 'Aditya',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['web', 'base_setup'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'my_backend_theme/static/src/scss/variables.scss',
            'my_backend_theme/static/src/scss/backend.scss',
            'my_backend_theme/static/src/js/theme_config.js',
            'my_backend_theme/static/src/js/theme_plugin.js',
        ],
    },
    'installable': True,
    'application': False,
}
