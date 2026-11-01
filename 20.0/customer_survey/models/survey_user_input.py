from odoo import api, fields, models


class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    customer_partner_id = fields.Many2one(
        'res.partner', 'Customer', index='btree_not_null', compute='_compute_customer_partner_id',
        store=True, readonly=False, precompute=True,
        help='The customer this answer is about. For a survey filled in during a visit, the participant is the '
             'employee and the customer is set here.')
    customer_mode = fields.Selection([
        ('email', 'Sent by e-mail'),
        ('visit', 'Filled in with the customer'),
    ], 'Collected', readonly=True)
    customer_collected_by_id = fields.Many2one('res.users', 'Collected by', readonly=True)
    # an average is what makes sense when grouping scores (pivot, graph, list groups)
    scoring_percentage = fields.Float(aggregator='avg')
    customer_country_id = fields.Many2one(related='customer_partner_id.country_id', store=True, string='Country')
    customer_salesperson_id = fields.Many2one(related='customer_partner_id.user_id', store=True,
                                              string='Salesperson')
    customer_commercial_id = fields.Many2one(related='customer_partner_id.commercial_partner_id', store=True,
                                             string='Company')

    @api.depends('partner_id')
    def _compute_customer_partner_id(self):
        for answer in self:
            if not answer.customer_partner_id and answer.partner_id and not answer.partner_id.user_ids.filtered(
                    lambda u: not u.share):
                # answers of employees are not customer answers, unless set explicitly (visit)
                answer.customer_partner_id = answer.partner_id

    def action_customer_resume(self):
        """ Continue an answer in progress (visit mode: the employee who started it). """
        self.ensure_one()
        return self.survey_id.action_start_survey(answer=self) | {'target': 'new'}
