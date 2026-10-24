from random import randint

from odoo import fields, models


class MailActivityTag(models.Model):
    _name = 'mail.activity.tag'
    _description = 'Activity tag'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer(default=lambda self: randint(1, 11))
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', help='Leave empty to share the tag between companies.')

    _name_uniq = models.UniqueIndex('(name, COALESCE(company_id, 0))', 'This tag already exists.')
