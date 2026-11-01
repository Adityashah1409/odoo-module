{
    'name': 'Customer Surveys',
    'summary': 'Run surveys from the customer: send them by e-mail, fill them in with the customer during a '
               'visit, print blank forms, follow answers and scores on the contact and analyse them',
    'version': '20.0.1.0.0',
    'category': 'Marketing/Surveys',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['contacts', 'survey'],
    'data': [
        'views/survey_user_input_views.xml',
        'views/res_partner_views.xml',
        'views/survey_survey_views.xml',
    ],
    'installable': True,
}
