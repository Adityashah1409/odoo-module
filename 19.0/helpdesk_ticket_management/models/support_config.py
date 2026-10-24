from random import randint

from odoo import api, fields, models


class SupportTicketType(models.Model):
    _name = 'support.ticket.type'
    _description = 'Ticket type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('UNIQUE(name)', 'This ticket type already exists.')


class SupportCategory(models.Model):
    _name = 'support.category'
    _description = 'Ticket category'
    _parent_name = 'parent_id'
    _parent_store = True
    _rec_name = 'complete_name'
    _order = 'complete_name'

    name = fields.Char(required=True, translate=True)
    complete_name = fields.Char(compute='_compute_complete_name', store=True, recursive=True)
    parent_id = fields.Many2one('support.category', string='Parent category', index=True, ondelete='cascade')
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many('support.category', 'parent_id', string='Sub-categories')
    active = fields.Boolean(default=True)

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        for category in self:
            category.complete_name = (f'{category.parent_id.complete_name} / {category.name}'
                                      if category.parent_id else category.name)


class SupportTag(models.Model):
    _name = 'support.tag'
    _description = 'Ticket tag'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer(default=lambda self: randint(1, 11))
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint('UNIQUE(name)', 'This tag already exists.')
