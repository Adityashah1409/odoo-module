import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 2

SUGGESTED_MODELS = [
    'res.partner', 'crm.lead', 'sale.order', 'account.move', 'purchase.order',
    'project.project', 'project.task', 'product.template', 'hr.employee',
]


class MyThemeSearchModel(models.Model):
    """A model included in the theme's global search."""

    _name = 'my.theme.search.model'
    _description = 'Backend Theme Global Search Model'
    _order = 'sequence, id'

    model_id = fields.Many2one(
        'ir.model', string="Model", required=True, ondelete='cascade',
        domain=[('transient', '=', False)],
    )
    model = fields.Char(related='model_id.model', store=True, string="Model Name")
    name = fields.Char(related='model_id.name', string="Label")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _unique_model = models.Constraint('UNIQUE(model_id)', "This model is already searchable.")

    @api.model
    def _add_suggested_entries(self):
        existing = set(self.with_context(active_test=False).search([]).mapped('model'))
        for sequence, model in enumerate(SUGGESTED_MODELS, start=1):
            if model not in existing and model in self.env:
                self.create({'model_id': self.env['ir.model']._get_id(model), 'sequence': sequence * 10})

    @api.model
    def global_search(self, query):
        """Search the configured models for ``query``.

        Runs as the current user, so access rights, record rules and the
        active companies (from the context) decide what is found. Models the
        user cannot read are skipped.
        """
        config = self.env['my.theme.config']._get_global_config()
        query = (query or '').strip()
        if not config['enable_global_search'] or len(query) < MIN_QUERY_LENGTH:
            return []
        if not self.has_access('read'):
            return []
        limit = config['search_limit']
        groups = []
        for entry in self.search([]):
            model_name = entry.model
            if model_name not in self.env:
                continue
            Model = self.env[model_name]
            if not Model.has_access('read'):
                continue
            try:
                # A savepoint keeps the transaction usable if the search fails.
                with self.env.cr.savepoint():
                    matches = Model.name_search(query, limit=limit)
            except Exception:
                # One misbehaving model must not break the whole search.
                _logger.warning("Global search failed on model %s", model_name, exc_info=True)
                continue
            if matches:
                groups.append({
                    'model': model_name,
                    'label': entry.name,
                    'records': [{'id': rec_id, 'name': name} for rec_id, name in matches],
                })
        return groups
