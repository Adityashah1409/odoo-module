from odoo import fields, models


class SupportStage(models.Model):
    _name = 'support.stage'
    _description = 'Helpdesk stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)
    fold = fields.Boolean('Folded in kanban', help='Folded stages are hidden from the kanban by default.')
    is_closed = fields.Boolean('Closing stage', help='Tickets in this stage are solved or cancelled.')
    team_ids = fields.Many2many('support.team', string='Teams',
                                help='Teams that use this stage. Leave empty for every team.')
    template_id = fields.Many2one(
        'mail.template', string='E-mail template', domain=[('model', '=', 'support.ticket')],
        help='Sent to the customer when a ticket reaches this stage.')
    color = fields.Char(default='#64748b', help='Colour used on the dashboard.')
