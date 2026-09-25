import logging

from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)

# Cookie the web client keeps in sync with the device's color scheme, so the
# server can pick the right stylesheet for users who follow their device.
DEVICE_SCHEME_COOKIE = 'mbt_device_scheme'


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

    def color_scheme(self):
        scheme = super().color_scheme()
        try:
            user = self.env.user
            if not request or not request.session.uid or not user._is_internal():
                return scheme
            mode = user._mbt_get_theme_mode()
            if mode == 'system':
                mode = request.cookies.get(DEVICE_SCHEME_COOKIE)
            if mode in ('light', 'dark'):
                return mode
        except Exception:
            _logger.exception("Could not compute the backend color scheme")
        return scheme
