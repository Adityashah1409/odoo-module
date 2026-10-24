from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestActivityTour(HttpCase):

    def test_dashboard_tour(self):
        admin = self.env.ref('base.user_admin')
        partner = self.env['res.partner'].create({'name': 'Tour Customer'})
        today = fields.Date.context_today(self.env['mail.activity'])
        self.env['mail.activity'].search([('user_id', '=', admin.id)]).unlink()
        self.env['mail.activity'].create({
            'res_model_id': self.env['ir.model']._get_id('res.partner'),
            'res_id': partner.id,
            'activity_type_id': self.env.ref('mail.mail_activity_data_call').id,
            'summary': 'Tour call',
            'user_id': admin.id,
            'date_deadline': today,
        })
        self.start_tour('/odoo/activity-dashboard', 'activity_management_tour', login='admin')
        activity = self.env['mail.activity'].with_context(active_test=False).search([('summary', '=', 'Tour call')])
        self.assertEqual(activity.progress, 'done')
        self.assertIn('Called from the tour', str(activity.feedback))
