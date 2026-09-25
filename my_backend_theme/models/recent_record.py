from odoo import api, fields, models


class MyThemeRecentRecord(models.Model):
    _name = 'my.theme.recent'
    _inherit = ['my.theme.record.link.mixin']
    _description = 'Backend Theme Recently Viewed Record'
    _order = 'last_viewed desc, id desc'

    user_id = fields.Many2one(
        'res.users', required=True, index=True, ondelete='cascade',
        default=lambda self: self.env.user,
    )
    res_model = fields.Char(string="Model", required=True)
    res_id = fields.Many2oneReference(model_field='res_model', string="Record", required=True)
    name = fields.Char(required=True)
    last_viewed = fields.Datetime(required=True, default=fields.Datetime.now, index=True)

    _unique_user_record = models.Constraint(
        'UNIQUE(user_id, res_model, res_id)',
        "A record is listed once per user.",
    )

    @api.model
    def _get_limit(self):
        return self.env['my.theme.config']._get_global_config()['recent_limit']

    @api.model
    def track(self, res_model, res_id):
        """Remember that the current user opened a record. Records the user
        cannot read are ignored. Old entries beyond the limit are deleted."""
        if not self._is_valid_business_model(res_model) or not isinstance(res_id, int):
            return False
        config = self.env['my.theme.config']._get_global_config()
        if not config['enable_recent']:
            return False
        record = self.env[res_model].browse(res_id).exists()
        if not record or not record.has_access('read'):
            return False
        values = {'name': record.display_name or '', 'last_viewed': fields.Datetime.now()}
        entry = self.search([
            ('user_id', '=', self.env.uid), ('res_model', '=', res_model), ('res_id', '=', res_id),
        ], limit=1)
        # Re-created rather than updated: dates are stored to the second, so
        # the newest id breaks ties between records opened in the same second.
        entry.unlink()
        self.create({**values, 'res_model': res_model, 'res_id': res_id})
        self.search([('user_id', '=', self.env.uid)], offset=config['recent_limit']).unlink()
        return True

    @api.model
    def get_recent(self):
        entries = self.search([('user_id', '=', self.env.uid)], limit=self._get_limit())
        entries = entries._filter_accessible()
        return [{
            'id': entry.id,
            'name': entry.name,
            'res_model': entry.res_model,
            'res_id': entry.res_id,
            'model_name': self.env['ir.model']._get(entry.res_model).name,
            'last_viewed': fields.Datetime.to_string(entry.last_viewed),
        } for entry in entries]

    @api.model
    def clear_recent(self):
        self.search([('user_id', '=', self.env.uid)]).unlink()
        return True
