{
    'name': 'Payslip Distribution by E-mail',
    'summary': 'Distribute payslip PDFs from your payroll provider: import a month of PDFs, match them to '
               'employees, e-mail them (optionally password-protected), schedule the sending, and let '
               'employees find their payslips in Odoo',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Employees',
    'author': 'Aditya Shah',
    'website': 'https://github.com/Adityashah1409/odoo-module',
    'license': 'LGPL-3',
    'depends': ['hr', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'data/payslip_data.xml',
        'data/mail_template_data.xml',
        'views/hr_payslip_document_views.xml',
        'views/hr_payslip_document_batch_views.xml',
        'views/hr_employee_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/payslip_import_wizard_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
}
