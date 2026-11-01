from odoo import api, fields, models

from .res_partner import PARTS


class ResUsers(models.Model):
    _inherit = 'res.users'

    first_name = fields.Char(related='partner_id.first_name', inherited=True, readonly=False, user_writeable=True)
    middle_name = fields.Char(related='partner_id.middle_name', inherited=True, readonly=False,
                              user_writeable=True)
    last_name = fields.Char(related='partner_id.last_name', inherited=True, readonly=False, user_writeable=True)

    @api.model_create_multi
    def create(self, vals_list):
        Partner = self.env['res.partner']
        for vals in vals_list:
            if not vals.get('name') and any(vals.get(key) for key in PARTS):
                vals['name'] = Partner._partner_names_join(*(vals.get(key) for key in PARTS))
        return super(ResUsers, self.with_context(partner_names_person=True)).create(vals_list)
