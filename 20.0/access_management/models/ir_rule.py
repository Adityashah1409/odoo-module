from odoo import api, models
from odoo.exceptions import AccessError


class Base(models.AbstractModel):
    """Odoo 20 merged ir.model.access and ir.rule into ir.access: every model computes its own
    security domain in ``_access_domain``; access rules add theirs on top."""
    _inherit = 'base'

    @api.model
    def _access_domain(self, operation):
        domain = super()._access_domain(operation)
        extra = self.env['access.rule']._restriction_domain(self._name, operation)
        if extra is None or domain.is_false():
            return domain
        return (domain & extra).optimize(self)

    def _make_access_error_message(self, operation, domain):
        error = super()._make_access_error_message(operation, domain)
        if self.env['access.rule']._restriction_domain(self._name, operation) is not None:
            message = error.args[0] if error.args else ''
            return AccessError(self.env._('%(message)s\n\n(Restricted by Access Management.)', message=message))
        return error
