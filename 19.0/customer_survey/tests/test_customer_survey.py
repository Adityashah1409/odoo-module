from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged


class CustomerSurveyCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.officer = new_test_user(cls.env, 'cs_officer', name='Olivia Officer', email='olivia@example.com',
                                    groups='base.group_user,survey.group_survey_user,base.group_partner_manager')
        cls.survey = cls.env['survey.survey'].create({
            'title': 'Customer satisfaction',
            'access_mode': 'token',
            'customer_default': True,
            'question_and_page_ids': [Command.create({
                'title': 'How satisfied are you with our service?',
                'question_type': 'simple_choice',
                'suggested_answer_ids': [Command.create({'value': v}) for v in ('Very', 'Somewhat', 'Not at all')],
            })],
        })
        cls.other_survey = cls.env['survey.survey'].create({
            'title': 'Delivery feedback', 'access_mode': 'token',
            'question_and_page_ids': [Command.create({'title': 'Comments', 'question_type': 'text_box'})],
        })
        cls.company = cls.env['res.partner'].create({'name': 'Delta Logistics', 'is_company': True})
        cls.customer = cls.env['res.partner'].create({'name': 'Nora Vermeulen', 'email': 'nora@example.com',
                                                      'parent_id': cls.company.id})
        cls.customer2 = cls.env['res.partner'].create({'name': 'Ravi Menon', 'email': 'ravi@example.com'})


class TestCustomerSurvey(CustomerSurveyCommon):

    def test_single_default_survey(self):
        self.assertEqual(self.env['survey.survey']._customer_default_survey(), self.survey)
        self.other_survey.customer_default = True
        self.assertFalse(self.survey.customer_default)
        self.assertEqual(self.env['survey.survey']._customer_default_survey(), self.other_survey)

    def test_send_by_email(self):
        partners = (self.customer | self.customer2).with_user(self.officer)
        action = partners.action_customer_survey_send()
        self.assertEqual(action['res_model'], 'survey.invite')
        invite = self.env['survey.invite'].with_user(self.officer).with_context(action['context']).create({})
        self.assertEqual(invite.survey_id, self.survey)
        self.assertEqual(invite.partner_ids, self.customer | self.customer2)
        invite.action_invite()
        answers = self.env['survey.user_input'].search([('survey_id', '=', self.survey.id)])
        self.assertEqual(answers.customer_partner_id, self.customer | self.customer2)
        self.assertEqual(set(answers.mapped('customer_mode')), {'email'})
        self.assertEqual(answers.partner_id, self.customer | self.customer2)
        self.assertEqual(self.customer.with_user(self.officer).customer_survey_count, 1)
        # the contact's own survey wins over the default
        self.customer.customer_survey_id = self.other_survey
        action = self.customer.with_user(self.officer).action_customer_survey_send()
        self.assertEqual(action['context']['default_survey_id'], self.other_survey.id)

    def test_fill_in_with_customer(self):
        action = self.customer.with_user(self.officer).action_customer_survey_start()
        answer = self.env['survey.user_input'].search([('survey_id', '=', self.survey.id)])
        self.assertRecordValues(answer, [{
            'customer_partner_id': self.customer.id,
            'partner_id': self.officer.partner_id.id,
            'customer_mode': 'visit',
            'customer_collected_by_id': self.officer.id,
            'customer_commercial_id': self.company.id,
        }])
        self.assertIn(answer.access_token, action['url'])
        self.assertEqual(action['target'], 'new')
        # a second visit is a new answer, even with limited attempts
        self.survey.write({'is_attempts_limited': True, 'attempts_limit': 1})
        self.customer.with_user(self.officer).action_customer_survey_start()
        self.assertEqual(self.customer.with_user(self.officer).customer_survey_count, 2)
        resume = answer.with_user(self.officer).action_customer_resume()
        self.assertIn(answer.access_token, resume['url'])

    def test_stats_and_answers_action(self):
        self.customer.with_user(self.officer).action_customer_survey_start()
        answer = self.customer.customer_survey_answer_ids
        self.assertFalse(self.customer.customer_survey_last_date)
        answer._mark_done()
        self.customer.invalidate_recordset(['customer_survey_last_date'])
        self.assertTrue(self.customer.customer_survey_last_date)
        self.assertEqual(self.company.customer_survey_answer_ids, answer, 'the company shows its contacts\' answers')
        self.assertFalse(self.customer2.customer_survey_answer_ids)
        action = self.company.action_customer_survey_answers()
        self.assertIn(answer, self.env['survey.user_input'].search(action['domain']), 'answers of the contacts too')
        self.assertEqual(self.survey.customer_answer_count, 1)

    def test_employee_answers_are_not_customer_answers(self):
        answer = self.survey._create_answer(user=self.officer)
        self.assertFalse(answer.customer_partner_id)
        answer = self.survey._create_answer(partner=self.customer2)
        self.assertEqual(answer.customer_partner_id, self.customer2, 'native invitations count too')

    def test_no_survey(self):
        self.survey.customer_default = False
        with self.assertRaises(UserError):
            self.customer.action_customer_survey_start()
        self.customer.customer_survey_id = self.other_survey
        self.assertIn(self.other_survey.access_token, self.customer.action_customer_survey_print()['url'])

    def test_bulk_server_action(self):
        action = self.env.ref('customer_survey.action_partner_send_customer_survey')
        res = action.with_user(self.officer).with_context(
            active_model='res.partner', active_ids=(self.customer | self.customer2).ids).run()
        self.assertEqual(res['res_model'], 'survey.invite')
        self.assertEqual(res['context']['default_partner_ids'], (self.customer | self.customer2).ids)


@tagged('post_install', '-at_install')
class TestCustomerSurveyHttp(HttpCase, CustomerSurveyCommon):

    def test_employee_opens_visit_survey(self):
        """ The employee can open the survey started for the customer (no "wrong user" page). """
        action = self.customer.with_user(self.officer).action_customer_survey_start()
        self.authenticate('cs_officer', 'cs_officer')
        res = self.url_open(action['url'])
        self.assertEqual(res.status_code, 200)
        self.assertIn('Customer satisfaction', res.text)
        self.assertIn('o_survey_start', res.text)
        self.assertNotIn('Survey Access Error', res.text)
        # why the visit answer belongs to the employee: Odoo refuses an answer of another partner
        native = self.survey._create_answer(partner=self.customer2)
        res = self.url_open(f'{self.survey.get_start_url()}?answer_token={native.access_token}')
        self.assertIn('Survey Access Error', res.text)
