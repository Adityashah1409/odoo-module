from odoo import _, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    customer_survey_id = fields.Many2one(
        'survey.survey', 'Survey', groups='survey.group_survey_user',
        domain="[('active', '=', True), ('survey_type', 'in', ('survey', 'custom', 'assessment'))]",
        help='Survey used for this customer. Empty: the default customer survey.')
    customer_survey_answer_ids = fields.Many2many(
        'survey.user_input', string='Survey answers', compute='_compute_customer_survey_stats',
        groups='survey.group_survey_user', help='Answers of this contact and of its contacts.')
    customer_survey_count = fields.Integer('Surveys', compute='_compute_customer_survey_stats',
                                           groups='survey.group_survey_user')
    customer_survey_last_date = fields.Datetime('Last survey', compute='_compute_customer_survey_stats',
                                                groups='survey.group_survey_user')

    def _compute_customer_survey_stats(self):
        for partner in self:
            mine = self.env['survey.user_input'].search(
                [('customer_partner_id', 'child_of', partner.id), ('test_entry', '=', False)],
                order='create_date desc, id desc') if partner.id else self.env['survey.user_input']
            partner.customer_survey_answer_ids = mine
            done = mine.filtered(lambda a: a.state == 'done')
            partner.customer_survey_count = len(mine)
            partner.customer_survey_last_date = max(done.mapped(lambda a: a.end_datetime or a.create_date),
                                                    default=False)

    def _customer_survey(self):
        survey = self.customer_survey_id or self.env['survey.survey']._customer_default_survey()
        if not survey:
            raise UserError(_('Choose a survey on the contact, or mark a survey as "Default customer survey".'))
        return survey

    def action_customer_survey_send(self):
        """ Invite the selected contacts by e-mail (one survey for all: the first contact's or the default). """
        survey = self[:1]._customer_survey()
        return survey.with_context(default_partner_ids=self.ids, default_customer_mode='email').action_send_survey()

    def action_customer_survey_start(self):
        """ Fill in the survey now, with the customer (e.g. during a visit). """
        self.ensure_one()
        survey = self._customer_survey()
        survey.check_validity()
        answer = survey._create_answer(user=self.env.user, check_attempts=False, customer_partner_id=self.id,
                                       customer_mode='visit', customer_collected_by_id=self.env.uid)
        action = survey.action_start_survey(answer=answer)
        action['target'] = 'new'
        return action

    def action_customer_survey_print(self):
        self.ensure_one()
        return self._customer_survey().action_print_survey()

    def action_customer_survey_answers(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('customer_survey.action_customer_survey_answers')
        action['domain'] = [('customer_partner_id', 'child_of', self.id)]
        action['context'] = {'search_default_done': 0}
        return action
