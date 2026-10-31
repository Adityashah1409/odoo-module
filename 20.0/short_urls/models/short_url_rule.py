from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class ShortUrlRule(models.Model):
    _name = 'short.url.rule'
    _description = 'Short URL automatic rule'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one('ir.model', string='Create links for', required=True, ondelete='cascade',
                               domain=[('field_id.name', '=', 'website_url'), ('transient', '=', False)],
                               default=lambda self: self.env['ir.model']._get('website.page'))
    model = fields.Char(related='model_id.model', store=True)
    domain = fields.Char(default='[]', help='Only the records matching this filter get a short link.')
    published_only = fields.Boolean('Published records only', default=True)
    website_id = fields.Many2one('website', ondelete='cascade', help='Website of the links (empty = global).')
    channel_id = fields.Many2one('short.url.channel', string='Channel')
    add_utm = fields.Boolean('Add UTM tags')
    validity_days = fields.Integer('Validity (days)', help='0 = the website default.')
    link_ids = fields.One2many('short.url', 'rule_id')
    link_count = fields.Integer(compute='_compute_link_count')
    last_run = fields.Datetime(readonly=True)

    def _compute_link_count(self):
        counts = dict(self.env['short.url'].with_context(active_test=False)._read_group(
            [('rule_id', 'in', self.ids)], ['rule_id'], ['__count']))
        for rule in self:
            rule.link_count = counts.get(rule, 0)

    def _records(self):
        self.ensure_one()
        Model = self.env[self.model].sudo()
        domain = safe_eval(self.domain or '[]', {'uid': self.env.uid})
        if self.published_only:
            for name in ('is_published', 'website_published'):
                if name in Model._fields and Model._fields[name].store:
                    domain = domain + [(name, '=', True)]
                    break
        if self.website_id and 'website_id' in Model._fields:
            domain = domain + [('website_id', 'in', [self.website_id.id, False])]
        return Model.search(domain)

    def action_apply(self):
        ShortUrl = self.env['short.url'].sudo().with_context(active_test=False)
        created = 0
        for rule in self:
            records = rule._records()
            existing = set(ShortUrl.search([('rule_id', '=', rule.id), ('res_model', '=', rule.model),
                                            ('res_id', 'in', records.ids)]).mapped('res_id'))
            website = rule.website_id or self.env['website']._short_url_current()
            days = rule.validity_days or website.short_url_validity_days
            vals_list = []
            for record in records.filtered(lambda r: r.id not in existing):
                url = record.url if record._name == 'website.page' else record.website_url
                if not url or url.startswith('#'):
                    continue
                vals_list.append({
                    'name': record.display_name, 'target_url': url, 'website_id': rule.website_id.id,
                    'channel_id': rule.channel_id.id, 'add_utm': rule.add_utm, 'rule_id': rule.id,
                    'res_model': record._name, 'res_id': record.id,
                    'token': website._short_url_new_token(),
                    'date_expire': fields.Datetime.add(fields.Datetime.now(), days=days) if days else False,
                })
            ShortUrl.create(vals_list)
            created += len(vals_list)
            rule.last_run = fields.Datetime.now()
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': self.env._('%s short link(s) created.', created), 'type': 'success',
                           'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    def action_view_links(self):
        action = self.env['ir.actions.act_window']._for_xml_id('short_urls.action_short_url')
        action['domain'] = [('rule_id', 'in', self.ids)]
        action['context'] = {'active_test': False}
        return action

    @api.constrains('domain', 'model_id')
    def _check_domain(self):
        for rule in self:
            try:
                rule._records()
            except Exception as error:  # noqa: BLE001
                raise UserError(self.env._('Invalid filter: %s', error)) from error

    @api.model
    def _cron_apply(self):
        self.search([]).action_apply()
