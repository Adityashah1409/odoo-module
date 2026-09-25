from odoo import api, models


class MyThemeRecordLinkMixin(models.AbstractModel):
    """Helpers for theme records that point to a business record
    (``res_model`` + ``res_id``)."""

    _name = 'my.theme.record.link.mixin'
    _description = 'Backend Theme Record Link'

    @api.model
    def _is_valid_business_model(self, model_name):
        return (
            isinstance(model_name, str)
            and model_name in self.env
            and not self.env[model_name]._transient
            and not self.env[model_name]._abstract
        )

    def _filter_accessible(self):
        """Keep the entries whose record still exists and is readable by the
        current user, so revoked access or deleted records never show up."""
        accessible = self.browse()
        by_model = {}
        for entry in self:
            if entry.res_model and entry.res_id:
                by_model.setdefault(entry.res_model, set()).add(entry.res_id)
        readable = {}
        for model_name, ids in by_model.items():
            if not self._is_valid_business_model(model_name):
                readable[model_name] = set()
                continue
            records = self.env[model_name].browse(list(ids)).exists()
            readable[model_name] = set(records._filtered_access('read').ids)
        for entry in self:
            if not (entry.res_model and entry.res_id) or entry.res_id in readable.get(entry.res_model, ()):
                accessible |= entry
        return accessible
