from datetime import timedelta
from unittest.mock import patch

from odoo import fields, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


class VisitorCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'visitor_notify_host': True, 'visitor_max_hours': 10})
        cls.receptionist = new_test_user(cls.env, 'vis_reception', groups='visitor_management.group_visitor_user',
                                         name='Rita Reception')
        cls.host_user = new_test_user(cls.env, 'vis_host', groups='base.group_user', name='Hugo Host',
                                      email='hugo@example.com')
        cls.department = cls.env['hr.department'].create({'name': 'Sales'})
        cls.host = cls.env['hr.employee'].create({
            'name': 'Hugo Host', 'user_id': cls.host_user.id, 'department_id': cls.department.id,
            'company_id': cls.company.id,
        })
        cls.other_host = cls.env['hr.employee'].create({'name': 'Hidden Host', 'company_id': cls.company.id,
                                                        'visitor_kiosk_host': False})
        cls.meeting = cls.env.ref('visitor_management.visit_type_meeting')
        cls.contractor = cls.env.ref('visitor_management.visit_type_contractor')
        cls.escorted = cls.env.ref('visitor_management.visit_category_escorted')
        cls.room = cls.env['visitor.destination'].create({'name': 'Room Atlas', 'note': '1st floor'})

    def _visit(self, **vals):
        return self.env['visitor.visit'].with_user(self.receptionist).create(dict({
            'visitor_name': 'Nora Vermeulen', 'visitor_company': 'Delta Logistics',
            'email': 'nora@example.com', 'host_id': self.host.id, 'visit_type_id': self.meeting.id,
            'destination_id': self.room.id,
        }, **vals))


class TestVisitor(VisitorCommon):

    def test_create_reference_and_pass_code(self):
        visits = self._visit() | self._visit(visitor_name='Other')
        for visit in visits:
            self.assertTrue(visit.name.startswith('VIS/'))
            self.assertRegex(visit.pass_code, r'^[A-HJ-NP-Z2-9]{6}$')
        self.assertNotEqual(visits[0].pass_code, visits[1].pass_code)
        self.assertNotEqual(visits[0].name, visits[1].name)
        self.assertEqual(visits[0].state, 'planned')
        self.assertEqual(visits[0].department_id, self.department)

    def test_check_in_notifies_host_and_check_out(self):
        visit = self._visit()
        visit.action_check_in()
        self.assertEqual(visit.state, 'on_site')
        self.assertTrue(visit.check_in)
        message = visit.message_ids.filtered(lambda m: self.host.work_contact_id in m.partner_ids)
        self.assertTrue(message, 'the host is notified')
        self.assertIn('Nora Vermeulen', message.body)
        self.assertIn('Room Atlas', message.body)
        with self.assertRaises(UserError):
            visit.action_check_in()
        with patch.object(fields.Datetime, 'now', lambda: visit.check_in + timedelta(hours=1, minutes=30)):
            visit.action_check_out()
        self.assertEqual(visit.state, 'done')
        self.assertAlmostEqual(visit.duration, 1.5, places=2)
        with self.assertRaises(UserError):
            visit.action_cancel()

    def test_no_notification_when_disabled(self):
        self.company.visitor_notify_host = False
        visit = self._visit()
        visit.action_check_in()
        self.assertFalse(visit.message_ids.filtered(lambda m: self.host.work_contact_id in m.partner_ids))

    def test_cancel_and_reset(self):
        visit = self._visit()
        visit.action_cancel()
        self.assertEqual(visit.state, 'cancel')
        visit.action_reset()
        self.assertEqual(visit.state, 'planned')
        visit.action_check_in()
        visit.action_cancel()
        visit.action_reset()
        self.assertFalse(visit.check_in)

    def test_overstay_and_auto_check_out(self):
        visit = self._visit()
        visit.action_check_in()
        self.assertFalse(visit.overstay)
        visit.check_in = fields.Datetime.now() - timedelta(hours=3)
        visit.invalidate_recordset(['overstay'])
        self.assertTrue(visit.overstay, 'a meeting usually lasts 2 hours')
        visit.check_in = fields.Datetime.now() - timedelta(hours=11)
        recent = self._visit(visitor_name='Recent')
        recent.action_check_in()
        self.env['visitor.visit']._cron_auto_check_out()
        self.assertEqual(visit.state, 'done')
        self.assertTrue(visit.auto_checked_out)
        self.assertEqual(recent.state, 'on_site')
        self.company.visitor_max_hours = 0
        recent.check_in = fields.Datetime.now() - timedelta(days=3)
        self.env['visitor.visit']._cron_auto_check_out()
        self.assertEqual(recent.state, 'on_site', '0 = never')

    def test_partner_onchange_and_invitation(self):
        partner = self.env['res.partner'].create({'name': 'Jan Peeters', 'email': 'jan@example.com',
                                                  'phone': '+32 470 00 00 00',
                                                  'parent_id': self.env['res.partner'].create({
                                                      'name': 'Peeters NV', 'is_company': True}).id})
        visit = self.env['visitor.visit'].new({'partner_id': partner.id})
        visit._onchange_partner_id()
        self.assertEqual(visit.visitor_name, 'Jan Peeters')
        self.assertEqual(visit.visitor_company, 'Peeters NV')
        self.assertEqual(visit.email, 'jan@example.com')

        visit = self._visit(planned_date=fields.Datetime.now() + timedelta(days=1))
        action = visit.action_send_invitation()
        composer = self.env['mail.compose.message'].with_context(action['context']).create({})
        self.assertIn(visit.pass_code, composer.body)
        composer._action_send_mail()
        self.assertTrue(visit.invitation_sent)
        mail = self.env['mail.mail'].search([('model', '=', 'visitor.visit'), ('res_id', '=', visit.id)])
        self.assertIn('nora@example.com', mail.mapped('email_to') + mail.recipient_ids.mapped('email'))
        visit.email = False
        with self.assertRaises(UserError):
            visit.action_send_invitation()

    def test_check_out_before_check_in_refused(self):
        visit = self._visit()
        visit.action_check_in()
        with self.assertRaises(ValidationError):
            visit.write({'check_out': visit.check_in - timedelta(hours=1)})

    def test_access_rights(self):
        Type = self.env['visitor.visit.type'].with_user(self.receptionist)
        self.assertTrue(Type.search([]))
        with self.assertRaises(AccessError):
            Type.create({'name': 'New type'})
        employee_user = new_test_user(self.env, 'vis_employee', groups='base.group_user')
        with self.assertRaises(AccessError):
            self.env['visitor.visit'].with_user(employee_user).search([])
        visit = self._visit()
        with self.assertRaises(AccessError):
            visit.with_user(self.receptionist).unlink()
        # host employee readable for a receptionist without HR rights (public profile)
        self.assertEqual(visit.with_user(self.receptionist).host_id.name, 'Hugo Host')
        self.assertEqual(self.host.with_user(self.env.ref('base.user_admin')).visitor_visit_count, 1)

    def test_pass_report(self):
        visit = self._visit(category_id=self.escorted.id)
        html = self.env['ir.actions.report']._render_qweb_html('visitor_management.report_visitor_pass', visit.ids)[0]
        html = html.decode()
        self.assertIn(visit.pass_code, html)
        self.assertIn('data:image/png;base64,', html)
        self.assertIn('Must be escorted', html)

    def test_kiosk_methods(self):
        Visit = self.env['visitor.visit'].sudo()
        planned = self._visit()
        visit = Visit._kiosk_check_in(self.company, {'pass_code': ' %s ' % planned.pass_code.lower()})
        self.assertEqual(visit, planned)
        self.assertEqual(planned.state, 'on_site')
        with self.assertRaises(ValidationError):
            Visit._kiosk_check_in(self.company, {'pass_code': planned.pass_code})
        with self.assertRaises(ValidationError):
            Visit._kiosk_check_in(self.company, {'visitor_name': 'Walk In'})
        with self.assertRaises(ValidationError):
            Visit._kiosk_check_in(self.company, {'visitor_name': 'Walk In', 'host_id': self.other_host.id})
        walk_in = Visit._kiosk_check_in(self.company, {
            'visitor_name': 'Walk In', 'host_id': str(self.host.id), 'visit_type_id': str(self.contractor.id)})
        self.assertRecordValues(walk_in, [{'state': 'on_site', 'source': 'kiosk', 'host_id': self.host.id,
                                           'visit_type_id': False}])  # contractors are not offered on the kiosk
        Visit._kiosk_check_out(self.company, walk_in.pass_code)
        self.assertEqual(walk_in.state, 'done')
        with self.assertRaises(ValidationError):
            Visit._kiosk_check_out(self.company, walk_in.pass_code)


@tagged('post_install', '-at_install')
class TestVisitorKiosk(HttpCase, VisitorCommon):

    def _url(self, suffix=''):
        return f'/visitor/kiosk/{self.company.sudo().visitor_kiosk_token}{suffix}'

    def test_kiosk_pages(self):
        self.assertEqual(self.url_open('/visitor/kiosk/wrong-token').status_code, 404)
        res = self.url_open(self._url())
        self.assertEqual(res.status_code, 200)
        self.assertIn('Check in', res.text)
        res = self.url_open(self._url('/check-in'))
        self.assertIn('Hugo Host', res.text)
        self.assertNotIn('Hidden Host', res.text)

        self.authenticate(None, None)
        csrf = http.Request.csrf_token(self)
        res = self.url_open(self._url('/check-in'), data={
            'csrf_token': csrf, 'visitor_name': 'Walk In Visitor', 'visitor_company': 'ACME',
            'host_id': str(self.host.id), 'visit_type_id': str(self.meeting.id), 'purpose': 'Demo',
        })
        self.assertEqual(res.status_code, 200)
        visit = self.env['visitor.visit'].search([('visitor_name', '=', 'Walk In Visitor')])
        self.assertEqual(visit.state, 'on_site')
        self.assertIn(visit.pass_code, res.text)
        self.assertIn('Hugo Host has been told', res.text)
        notification = visit.message_ids.filtered(lambda m: self.host.work_contact_id in m.partner_ids)
        self.assertEqual(notification.author_id, self.company.partner_id, 'not the public user')

        res = self.url_open(self._url('/check-in'), data={'csrf_token': csrf, 'visitor_name': 'No host'})
        self.assertIn('Please choose the person you are visiting', res.text)
        self.assertIn('value="No host"', res.text, 'the form keeps what was typed')

        res = self.url_open(self._url('/check-out'), data={'csrf_token': csrf, 'pass_code': 'ZZZZZZ'})
        self.assertIn('No visitor on site', res.text)
        res = self.url_open(self._url('/check-out'), data={'csrf_token': csrf, 'pass_code': visit.pass_code})
        self.assertIn('Goodbye, Walk In Visitor', res.text)
        self.assertEqual(visit.state, 'done')
