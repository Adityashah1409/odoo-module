from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _handle_debug(cls):
        super()._handle_debug()
        if request.session.debug and request.session.uid:
            env = request.env(user=request.session.uid)
            restrictions = env['access.rule']._get_restrictions()
            if restrictions and restrictions['no_debug']:
                request.session.debug = ''
