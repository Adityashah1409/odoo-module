from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        if self.env.user._is_internal():
            result['chatter_message_order'] = self.env.user._chatter_effective_order()
        return result
