from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    support_portal_create = fields.Boolean(
        'Customers create tickets from the portal', config_parameter='helpdesk_ticket_management.portal_create')
    support_customer_reply_stage_id = fields.Many2one(
        'support.stage', string='When the customer answers, move to',
        config_parameter='helpdesk_ticket_management.customer_reply_stage_id')
    support_staff_reply_stage_id = fields.Many2one(
        'support.stage', string='When support answers, move to',
        config_parameter='helpdesk_ticket_management.staff_reply_stage_id')
    support_multi_timer = fields.Boolean(
        'Several timers per user', config_parameter='helpdesk_ticket_management.multi_timer',
        help='Let one person run timers on several tickets at the same time.')
    support_max_attachment_mb = fields.Integer(
        'Portal attachment limit (MB)', config_parameter='helpdesk_ticket_management.max_attachment_mb',
        help='Largest file a customer can attach when creating a ticket. 0 = no limit.')
