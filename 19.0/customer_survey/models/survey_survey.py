from odoo import api, fields, models


class SurveySurvey(models.Model):
    _inherit = 'survey.survey'

    customer_default = fields.Boolean(
        'Default customer survey',
        help='Proposed on contacts that have no survey of their own, and used when sending a survey to several '
             'contacts from the contact list.')
    customer_answer_count = fields.Integer('Customer answers', compute='_compute_customer_answer_count')

    def _compute_customer_answer_count(self):
        counts = dict(self.env['survey.user_input']._read_group(
            [('survey_id', 'in', self.ids), ('customer_partner_id', '!=', False), ('test_entry', '=', False)],
            ['survey_id'], ['__count']))
        for survey in self:
            survey.customer_answer_count = counts.get(survey, 0)

    @api.model
    def _customer_default_survey(self):
        return self.search([('customer_default', '=', True), ('active', '=', True)], limit=1)

    def write(self, vals):
        res = super().write(vals)
        if vals.get('customer_default'):
            # only one default
            self.search([('customer_default', '=', True), ('id', 'not in', self.ids)]).customer_default = False
        return res

    @api.model_create_multi
    def create(self, vals_list):
        surveys = super().create(vals_list)
        defaults = surveys.filtered('customer_default')
        if defaults:
            self.search([('customer_default', '=', True), ('id', 'not in', defaults[-1:].ids)]).customer_default = False
        return surveys

    def action_customer_answers(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('customer_survey.action_customer_survey_answers')
        action['domain'] = [('survey_id', '=', self.id), ('customer_partner_id', '!=', False)]
        return action
