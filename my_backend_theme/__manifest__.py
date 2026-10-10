{
    'name': 'Backend Theme',
    'version': '20.0.1.1.0',
    'category': 'Themes/Backend',
    'summary': 'Sidebar, dark mode, colors, accessibility, quick create, bookmarks, tabs, workspace and global search for the backend',
    'description': """
Configurable backend theme for the Odoo 20 web client: colors and presets,
dark mode, sidebar menu styles, list and form view styles, quick create,
bookmarks, recently viewed records, a personal workspace page, workspace
tabs, split view, global search, keyboard shortcuts, an accessibility mode and
settings import/export.
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
        'views/settings_transfer_views.xml',
        'views/workspace_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'my_backend_theme/static/src/scss/variables.scss',
            'my_backend_theme/static/src/scss/backend.scss',
            'my_backend_theme/static/src/scss/navbar.scss',
            'my_backend_theme/static/src/scss/views.scss',
            'my_backend_theme/static/src/scss/accessibility.scss',
            'my_backend_theme/static/src/js/**/*',
            'my_backend_theme/static/src/sidebar/**/*',
            'my_backend_theme/static/src/navigation/**/*',
            'my_backend_theme/static/src/tabs/**/*',
            'my_backend_theme/static/src/split_view/**/*',
            'my_backend_theme/static/src/commands/**/*',
            'my_backend_theme/static/src/workspace/**/*',
            'my_backend_theme/static/src/settings/**/*',
        ],
        # The dark stylesheet is Odoo's own `web.assets_web_dark` bundle, built
        # with the theme's dark palette defined before Odoo's defaults.
        'web.assets_unit_tests': [
            'my_backend_theme/static/tests/**/*',
            ('remove', 'my_backend_theme/static/tests/tours/**/*'),
        ],
        'web.assets_tests': [
            'my_backend_theme/static/tests/tours/**/*',
        ],
        'web.assets_web_dark': [
            ('before', 'web/static/src/scss/primary_variables.scss',
             'my_backend_theme/static/src/scss/dark/primary_variables.dark.scss'),
            'my_backend_theme/static/src/scss/dark/backend.dark.scss',
        ],
    },
    'installable': True,
    'application': False,
}
