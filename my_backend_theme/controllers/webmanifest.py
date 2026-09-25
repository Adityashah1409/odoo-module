import logging

from odoo.http import request

from odoo.addons.web.controllers.webmanifest import WebManifest

_logger = logging.getLogger(__name__)


class ThemeWebManifest(WebManifest):
    """Odoo's installable web app (PWA) takes the theme's navbar color."""

    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        try:
            config = request.env['my.theme.config'].sudo()._get_global_config()
        except Exception:
            _logger.exception("Could not read the backend theme for the web manifest.")
            return manifest
        # Colors are validated by _get_global_config (#rrggbb or False).
        color = config['navbar_color'] or config['primary_color']
        if color:
            manifest['theme_color'] = color
            manifest['background_color'] = color
        return manifest
