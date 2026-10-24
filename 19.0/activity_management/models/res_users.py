from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    activity_supervisor_id = fields.Many2one(
        'res.users', string='Activity supervisor', domain=[('share', '=', False)],
        help='Set as supervisor of the activities assigned to this user; the supervisor sees and follows them.')
    activity_team_ids = fields.One2many('res.users', 'activity_supervisor_id', string='Supervised users')

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ['activity_supervisor_id']
