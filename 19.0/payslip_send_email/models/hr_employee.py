from odoo import fields, models

from .res_company import EMAIL_MODES


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    payslip_email_mode = fields.Selection(
        [('company', 'Company setting')] + EMAIL_MODES + [('none', 'Do not e-mail (hand delivered)')],
        'Payslips by e-mail', default='company', required=True, groups='hr.group_hr_user')
    payslip_document_count = fields.Integer('Payslips', compute='_compute_payslip_document_count',
                                            groups='payslip_send_email.group_payslip_officer')

    def _compute_payslip_document_count(self):
        counts = dict(self.env['hr.payslip.document']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count']))
        for employee in self:
            employee.payslip_document_count = counts.get(employee, 0)

    def _payslip_email_addresses(self):
        """ Where to send the payslips of this employee (list of e-mails, maybe empty). """
        self.ensure_one()
        employee = self.sudo()
        mode = employee.payslip_email_mode
        if mode == 'none':
            return []
        if mode == 'company':
            mode = employee.company_id.payslip_email_mode
        private, work = employee.private_email, employee.work_email
        if mode == 'private':
            emails = [private]
        elif mode == 'work':
            emails = [work]
        elif mode == 'both':
            emails = [private, work]
        else:
            emails = [private or work]
        return list(dict.fromkeys(e.strip() for e in emails if e and e.strip()))

    def action_view_payslip_documents(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('payslip_send_email.action_payslip_document')
        action['domain'] = [('employee_id', '=', self.id)]
        action['context'] = {'default_employee_id': self.id}
        return action
