{
    'name': 'Event Seat Booking',
    'summary': 'Seat maps for events: layout designer, sections per ticket, premium rows, seat selection and '
               'best-seat allocation on the website, holds with timer, paid checkout, seat on tickets, waitlist, '
               'seat exchange from the portal, seating dashboard',
    'version': '20.0.1.0.0',
    'category': 'Marketing/Events',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['website_event_sale'],
    'data': [
        'security/ir.access.csv',
        'data/product_data.xml',
        'data/portal_entry_data.xml',
        'data/mail_template_data.xml',
        'data/ir_cron_data.xml',
        'views/event_seat_plan_views.xml',
        'views/event_seat_views.xml',
        'views/event_ticket_views.xml',
        'views/event_event_views.xml',
        'views/event_registration_views.xml',
        'views/event_seat_waitlist_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/event_seat_switch_views.xml',
        'views/website_templates.xml',
        'views/portal_templates.xml',
        'report/event_ticket_report.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'event_seat_booking/static/src/scss/seat_map.scss',
            'event_seat_booking/static/src/js/seat_map.js',
        ],
        'web.assets_backend': [
            'event_seat_booking/static/src/scss/seat_map.scss',
            'event_seat_booking/static/src/dashboard/**/*',
        ],
        'web.report_assets_common': [
            'event_seat_booking/static/src/scss/seat_map.scss',
        ],
        'web.assets_tests': [
            'event_seat_booking/static/tests/tours/**/*',
        ],
    },
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'application': False,
}
