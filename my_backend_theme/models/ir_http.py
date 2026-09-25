import logging

from odoo import models

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        try:
            result['backend_theme'] = self.env['my.theme.config']._get_global_config()
        except Exception:
            # A broken theme configuration must never prevent the backend from
            # loading: the web client falls back to Odoo's default look.
            _logger.exception("Could not load the backend theme configuration")
        return result
