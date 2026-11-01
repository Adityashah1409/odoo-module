from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    visitor_kiosk_host = fields.Boolean(
        'Can be chosen on the visitor kiosk', default=True, groups='hr.group_hr_user',
        help='Visitors checking in at the kiosk can pick this employee as their host.')
    visitor_visit_count = fields.Integer('Visits', compute='_compute_visitor_visit_count',
                                         groups='visitor_management.group_visitor_user')

    def _compute_visitor_visit_count(self):
        counts = dict(self.env['visitor.visit']._read_group(
            [('host_id', 'in', self.ids)], ['host_id'], ['__count']))
        for employee in self:
            employee.visitor_visit_count = counts.get(employee, 0)

    def action_view_visitor_visits(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('visitor_management.action_visitor_visit')
        action['domain'] = [('host_id', '=', self.id)]
        action['context'] = {'default_host_id': self.id}
        return action
