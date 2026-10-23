{
    'name': 'Fleet GPS Tracking (Traccar)',
    'summary': 'Live GPS positions, motion status, trips, odometer and events '
               'from a Traccar server on your Fleet vehicles, with a live map',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Fleet',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['fleet'],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron.xml',
        'views/traccar_server_views.xml',
        'views/traccar_device_views.xml',
        'views/traccar_history_views.xml',
        'views/fleet_vehicle_views.xml',
        'wizard/traccar_trip_import_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
}
