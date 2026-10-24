from odoo import fields, models


class SupportChecklistTemplate(models.Model):
    _name = 'support.checklist.template'
    _description = 'Checklist template'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    type_ids = fields.Many2many('support.ticket.type', string='Ticket types',
                                help='Loaded automatically on new tickets of these types.')
    line_ids = fields.One2many('support.checklist.template.line', 'template_id', string='Items', copy=True)


class SupportChecklistTemplateLine(models.Model):
    _name = 'support.checklist.template.line'
    _description = 'Checklist template item'
    _order = 'sequence, id'

    template_id = fields.Many2one('support.checklist.template', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True, translate=True)


class SupportTicketChecklist(models.Model):
    _name = 'support.ticket.checklist'
    _description = 'Ticket checklist item'
    _order = 'sequence, id'

    ticket_id = fields.Many2one('support.ticket', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    done = fields.Boolean()
    done_by_id = fields.Many2one('res.users', readonly=True)
    date_done = fields.Datetime(readonly=True)

    def write(self, vals):
        if 'done' in vals:
            vals.update({'done_by_id': self.env.uid if vals['done'] else False,
                         'date_done': fields.Datetime.now() if vals['done'] else False})
        return super().write(vals)
