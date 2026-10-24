from odoo import api, fields, models

from .hubspot_account import OBJECT_TYPES


class HubspotOwner(models.Model):
    _name = 'hubspot.owner'
    _description = 'HubSpot owner'
    _order = 'name'

    account_id = fields.Many2one('hubspot.account', required=True, ondelete='cascade', index=True)
    hubspot_id = fields.Char('Owner ID', required=True)
    name = fields.Char()
    email = fields.Char()
    user_id = fields.Many2one('res.users', string='Odoo user', domain=[('share', '=', False)])

    _owner_uniq = models.Constraint('UNIQUE(account_id, hubspot_id)', 'This owner already exists.')


class HubspotStage(models.Model):
    _name = 'hubspot.stage'
    _description = 'HubSpot deal stage'
    _order = 'pipeline_label, sequence'

    account_id = fields.Many2one('hubspot.account', required=True, ondelete='cascade', index=True)
    pipeline_id = fields.Char('Pipeline ID', required=True)
    pipeline_label = fields.Char('Pipeline')
    hubspot_id = fields.Char('Stage ID', required=True)
    name = fields.Char('Stage')
    sequence = fields.Integer()
    probability = fields.Float()
    is_closed = fields.Boolean('Closed')
    is_won = fields.Boolean('Won')
    crm_stage_id = fields.Many2one('crm.stage', string='Odoo stage')

    _stage_uniq = models.Constraint('UNIQUE(account_id, pipeline_id, hubspot_id)', 'This stage already exists.')


MAPPABLE_MODELS = {'companies': 'res.partner', 'contacts': 'res.partner', 'products': 'product.template',
                   'deals': 'crm.lead', 'quotes': 'sale.order', 'invoices': 'account.move'}


class HubspotFieldMapping(models.Model):
    _name = 'hubspot.field.mapping'
    _description = 'HubSpot custom field mapping'
    _order = 'object_type, id'

    account_id = fields.Many2one('hubspot.account', required=True, ondelete='cascade', index=True)
    active = fields.Boolean(default=True)
    object_type = fields.Selection([t for t in OBJECT_TYPES if t[0] in MAPPABLE_MODELS], required=True)
    model_name = fields.Char(compute='_compute_model_name')
    field_id = fields.Many2one('ir.model.fields', string='Odoo field', required=True, ondelete='cascade',
                               domain="[('model', '=', model_name), ('store', '=', True), "
                                      "('ttype', 'in', ('char', 'text', 'html', 'integer', 'float', 'monetary', "
                                      "'boolean', 'date', 'datetime', 'selection', 'many2one'))]")
    hubspot_property = fields.Char('HubSpot property', required=True,
                                   help='Internal name of the HubSpot property, e.g. customer_reference.')
    direction = fields.Selection([('both', 'Both ways'), ('import', 'HubSpot → Odoo'), ('export', 'Odoo → HubSpot')],
                                 default='both', required=True)

    @api.depends('object_type')
    def _compute_model_name(self):
        for mapping in self:
            mapping.model_name = MAPPABLE_MODELS.get(mapping.object_type)


class HubspotLog(models.Model):
    _name = 'hubspot.log'
    _description = 'HubSpot synchronization run'
    _order = 'id desc'

    account_id = fields.Many2one('hubspot.account', required=True, ondelete='cascade', index=True)
    direction = fields.Selection([('import', 'Import'), ('export', 'Export'), ('webhook', 'Webhook')], required=True)
    object_type = fields.Selection(OBJECT_TYPES)
    date_start = fields.Datetime(default=fields.Datetime.now, required=True)
    date_end = fields.Datetime()
    queued = fields.Integer('Queued')
    job_ids = fields.One2many('hubspot.queue', 'log_id', string='Jobs')
    created = fields.Integer(compute='_compute_results')
    updated = fields.Integer(compute='_compute_results')
    skipped = fields.Integer(compute='_compute_results')
    failed = fields.Integer(compute='_compute_results')
    pending = fields.Integer(compute='_compute_results')

    @api.depends('direction', 'object_type', 'date_start')
    def _compute_display_name(self):
        directions = dict(self._fields['direction']._description_selection(self.env))
        objects = dict(self._fields['object_type']._description_selection(self.env))
        for log in self:
            log.display_name = ' '.join(filter(None, [directions.get(log.direction), objects.get(log.object_type),
                                                      fields.Datetime.to_string(log.date_start)]))

    def _compute_results(self):
        counts = {}
        for log, state, result, count in self.env['hubspot.queue']._read_group(
                [('log_id', 'in', self.ids)], ['log_id', 'state', 'result'], ['__count']):
            key = 'failed' if state == 'failed' else 'pending' if state == 'pending' else (result or 'skipped')
            if key in ('archived',):
                key = 'updated'
            counts.setdefault(log.id, {}).setdefault(key, 0)
            counts[log.id][key] += count
        for log in self:
            values = counts.get(log.id, {})
            for key in ('created', 'updated', 'skipped', 'failed', 'pending'):
                log[key] = values.get(key, 0)

    @api.model
    def _cron_cleanup(self, days=60):
        limit = fields.Datetime.subtract(fields.Datetime.now(), days=days)
        self.env['hubspot.queue'].search([('state', 'in', ('done', 'skipped')), ('write_date', '<', limit)]).unlink()
        self.search([('date_start', '<', limit), ('job_ids', '=', False)]).unlink()
