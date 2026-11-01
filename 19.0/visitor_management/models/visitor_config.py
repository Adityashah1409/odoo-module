from odoo import fields, models


class VisitorVisitType(models.Model):
    _name = 'visitor.visit.type'
    _description = 'Visit type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    active = fields.Boolean(default=True)
    kiosk = fields.Boolean('Offered on the kiosk', default=True)
    expected_hours = fields.Float('Usual duration', help='Used to flag visits that last longer than expected.')


class VisitorVisitCategory(models.Model):
    _name = 'visitor.visit.category'
    _description = 'Visitor category'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    active = fields.Boolean(default=True)
    escort = fields.Boolean('Must be escorted', help='Printed on the visitor pass.')


class VisitorDestination(models.Model):
    _name = 'visitor.destination'
    _description = 'Visit destination'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    note = fields.Char('Directions', help='Printed on the visitor pass, e.g. "2nd floor, left of the lifts".')
