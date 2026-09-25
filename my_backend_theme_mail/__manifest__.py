{
    'name': 'Backend Theme - Discuss',
    'version': '20.0.1.0.0',
    'category': 'Themes/Backend',
    'summary': 'Chatter position setting of the Backend Theme',
    'description': """
Glue module installed automatically when both Backend Theme and Discuss
(mail) are installed. It applies the theme's chatter position setting, so the
main theme does not have to depend on Discuss.
""",
    'author': 'Aditya',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['my_backend_theme', 'mail'],
    'auto_install': True,
    'assets': {
        'web.assets_backend': [
            'my_backend_theme_mail/static/src/**/*',
        ],
    },
    'installable': True,
}
