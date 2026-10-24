from odoo import api, models
from odoo.exceptions import AccessError
from odoo.fields import Domain


class IrRule(models.Model):
    _inherit = 'ir.rule'

    @api.model
    def _compute_domain(self, model_name, mode='read'):
        domain = super()._compute_domain(model_name, mode)
        extra = self.env['access.rule']._restriction_domain(model_name, mode)
        if extra is None:
            return domain
        return Domain.AND([domain, extra]).optimize(self.env[model_name])

    def _make_access_error(self, operation, records):
        error = super()._make_access_error(operation, records)
        if self.env['access.rule']._restriction_domain(records._name, operation) is not None:
            message = error.args[0] if error.args else ''
            return AccessError(self.env._('%(message)s\n\n(Restricted by Access Management.)', message=message))
        return error
