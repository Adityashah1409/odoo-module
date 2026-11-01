from odoo import api, models

from .res_partner import PARTS


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model_create_multi
    def create(self, vals_list):
        Partner = self.env['res.partner']
        for vals in vals_list:
            if not vals.get('name') and any(vals.get(key) for key in PARTS):
                vals['name'] = Partner._partner_names_join(*(vals.get(key) for key in PARTS))
        return super(ResUsers, self.with_context(partner_names_person=True)).create(vals_list)

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + list(PARTS)
