{
    'name': 'Backend Theme',
    'version': '20.0.1.0.0',
    'category': 'Themes/Backend',
    'summary': 'Sidebar, dark mode, colors, quick create, bookmarks, tabs and global search for the backend',
    'description': """
Configurable backend theme for the Odoo 20 web client: colors and presets,
dark mode, sidebar menu styles, list and form view styles, quick create,
bookmarks, recently viewed records, workspace tabs, split view, global search
and keyboard shortcuts.
""",
    'author': 'Aditya',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['web', 'base_setup'],
    'data': [
        'security/ir.access.csv',
        'data/theme_data.xml',
        'views/theme_menus.xml',
        'views/res_config_settings_views.xml',
        'views/res_users_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'my_backend_theme/static/src/scss/variables.scss',
            'my_backend_theme/static/src/scss/backend.scss',
            'my_backend_theme/static/src/scss/navbar.scss',
            'my_backend_theme/static/src/scss/views.scss',
            'my_backend_theme/static/src/js/**/*',
            'my_backend_theme/static/src/sidebar/**/*',
            'my_backend_theme/static/src/navigation/**/*',
            'my_backend_theme/static/src/tabs/**/*',
            'my_backend_theme/static/src/split_view/**/*',
            'my_backend_theme/static/src/commands/**/*',
        ],
        # The dark stylesheet is Odoo's own `web.assets_web_dark` bundle, built
        # with the theme's dark palette defined before Odoo's defaults.
        'web.assets_web_dark': [
            ('before', 'web/static/src/scss/primary_variables.scss',
             'my_backend_theme/static/src/scss/dark/primary_variables.dark.scss'),
            'my_backend_theme/static/src/scss/dark/backend.dark.scss',
        ],
    },
    'installable': True,
    'application': False,
}
