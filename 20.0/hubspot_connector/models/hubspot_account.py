import logging
import secrets
from datetime import timedelta

from odoo import api, fields, models

from .hubspot_client import HubspotClient, HubspotError, from_hubspot_datetime

_logger = logging.getLogger(__name__)

EXPORT_OVERLAP_MINUTES = 5
OBJECT_TYPES = [
    ('companies', 'Companies'),
    ('contacts', 'Contacts'),
    ('products', 'Products'),
    ('deals', 'Deals'),
    ('quotes', 'Quotes'),
    ('invoices', 'Invoices'),
    ('notes', 'Notes'),
    ('tasks', 'Tasks'),
    ('meetings', 'Meetings'),
    ('emails', 'E-mails'),
]
# HubSpot object type ids, used for record links and generic webhooks
OBJECT_TYPE_IDS = {'contacts': '0-1', 'companies': '0-2', 'deals': '0-3', 'products': '0-7', 'quotes': '0-14',
                   'invoices': '0-53'}


class HubspotAccount(models.Model):
    _name = 'hubspot.account'
    _description = 'HubSpot account'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    name = fields.Char(required=True, tracking=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    access_token = fields.Char(
        'Private app token', groups='hubspot_connector.group_hubspot_manager', copy=False,
        help='HubSpot > Settings > Integrations > Private Apps > your app > Access token.')
    state = fields.Selection([('draft', 'Not tested'), ('connected', 'Connected'), ('error', 'Error')],
                             default='draft', required=True, readonly=True, tracking=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)
    portal_id = fields.Char('HubSpot account ID', readonly=True, copy=False)
    ui_domain = fields.Char(readonly=True, copy=False, default='app.hubspot.com')
    hubspot_currency = fields.Char('HubSpot currency', readonly=True, copy=False)
    deal_type = fields.Selection([('lead', 'Lead'), ('opportunity', 'Opportunity')], string='Import deals as',
                                 default='opportunity', required=True)
    pipeline_id = fields.Char('Deal pipeline', default='default',
                              help='HubSpot pipeline used for deals exported from Odoo.')
    conflict_policy = fields.Selection(
        [('hubspot', 'HubSpot wins'), ('odoo', 'Odoo wins')], default='hubspot', required=True,
        help='When a record changed on both sides since the last synchronization.')
    default_user_id = fields.Many2one('res.users', string='Default user', domain=[('share', '=', False)],
                                      help='Assigned to imported tasks and meetings whose HubSpot owner is not mapped.')
    fallback_product_id = fields.Many2one(
        'product.product', string='Fallback product',
        help='Used for quote and invoice line items that have no product in HubSpot.')
    batch_size = fields.Integer('Jobs per run', default=200, help='Queue jobs processed by each scheduled run.')
    max_attempts = fields.Integer('Attempts before failing', default=3)
    auto_sync = fields.Boolean('Scheduled synchronization', default=True,
                               help='Import and export the enabled objects on each scheduled run.')
    webhook_secret = fields.Char('App client secret', groups='hubspot_connector.group_hubspot_manager', copy=False,
                                 help='Used to check the signature of webhook calls (X-HubSpot-Signature-v3).')
    webhook_url = fields.Char(compute='_compute_webhook_url')
    object_ids = fields.One2many('hubspot.object', 'account_id', string='Objects', copy=True)
    owner_ids = fields.One2many('hubspot.owner', 'account_id', string='Owners')
    stage_ids = fields.One2many('hubspot.stage', 'account_id', string='Deal stages')
    mapping_ids = fields.One2many('hubspot.field.mapping', 'account_id', string='Field mappings', copy=True)
    pending_count = fields.Integer(compute='_compute_counts')
    failed_count = fields.Integer(compute='_compute_counts')
    link_count = fields.Integer(compute='_compute_counts')

    @api.model_create_multi
    def create(self, vals_list):
        accounts = super().create(vals_list)
        for account in accounts:
            missing = {key for key, _label in OBJECT_TYPES} - set(account.object_ids.mapped('object_type'))
            self.env['hubspot.object'].create([
                {'account_id': account.id, 'object_type': key, 'sequence': index * 10,
                 'import_enabled': key not in ('quotes', 'invoices'), 'export_enabled': False}
                for index, (key, _label) in enumerate(OBJECT_TYPES) if key in missing])
        return accounts

    def _compute_webhook_url(self):
        base = self.env['ir.config_parameter'].sudo().get_str('web.base.url', '')
        for account in self:
            account.webhook_url = f'{base}/hubspot/webhook/{account.id}' if account.id else False

    def _compute_counts(self):
        Queue = self.env['hubspot.queue']
        pending = dict(Queue._read_group([('account_id', 'in', self.ids), ('state', '=', 'pending')],
                                         ['account_id'], ['__count']))
        failed = dict(Queue._read_group([('account_id', 'in', self.ids), ('state', '=', 'failed')],
                                        ['account_id'], ['__count']))
        links = dict(self.env['hubspot.record']._read_group([('account_id', 'in', self.ids)], ['account_id'],
                                                            ['__count']))
        for account in self:
            account.pending_count = pending.get(account, 0)
            account.failed_count = failed.get(account, 0)
            account.link_count = links.get(account, 0)

    # ------------------------------------------------------------------ client
    def _client(self):
        self.ensure_one()
        return HubspotClient(self.sudo().access_token)

    def _record_url(self, object_type, hubspot_id):
        self.ensure_one()
        if object_type not in OBJECT_TYPE_IDS or not self.portal_id:
            return False
        return (f'https://{self.ui_domain or "app.hubspot.com"}/contacts/{self.portal_id}'
                f'/record/{OBJECT_TYPE_IDS[object_type]}/{hubspot_id}')

    # ------------------------------------------------------------------ setup
    def action_test_connection(self):
        for account in self:
            try:
                info = account._client().account_info()
            except HubspotError as error:
                account.write({'state': 'error', 'last_error': str(error)})
                continue
            account.write({
                'state': 'connected', 'last_error': False, 'portal_id': str(info.get('portalId') or ''),
                'ui_domain': info.get('uiDomain') or 'app.hubspot.com',
                'hubspot_currency': info.get('companyCurrency') or False,
            })
            account.action_fetch_metadata()
        if len(self) == 1:
            ok = self.state == 'connected'
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'type': 'success' if ok else 'danger',
                'title': self.env._('HubSpot'),
                'message': self.env._('Connected to HubSpot account %s.', self.portal_id) if ok else self.last_error,
                'sticky': not ok, 'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}
        return True

    def action_fetch_metadata(self):
        """Owners (matched to users by e-mail) and deal pipelines (matched to CRM stages by name)."""
        for account in self:
            client = account._client()
            Owner = self.env['hubspot.owner']
            existing = {o.hubspot_id: o for o in account.owner_ids}
            users = self.env['res.users'].search([('share', '=', False)])
            for data in client.owners():
                vals = {'account_id': account.id, 'hubspot_id': str(data['id']), 'email': data.get('email'),
                        'name': ' '.join(filter(None, [data.get('firstName'), data.get('lastName')])) or data.get('email')}
                owner = existing.get(str(data['id']))
                if owner:
                    owner.write(vals)
                else:
                    email = (data.get('email') or '').lower()
                    vals['user_id'] = users.filtered(lambda u: (u.email or u.login or '').lower() == email)[:1].id
                    Owner.create(vals)
            Stage = self.env['hubspot.stage']
            existing = {(s.pipeline_id, s.hubspot_id): s for s in account.stage_ids}
            crm_stages = self.env['crm.stage'].search([])
            for pipeline in client.pipelines('deals'):
                for stage in pipeline.get('stages', []):
                    meta = stage.get('metadata') or {}
                    probability = float(meta.get('probability') or 0)
                    closed = str(meta.get('isClosed')).lower() == 'true'
                    vals = {'account_id': account.id, 'pipeline_id': pipeline['id'], 'pipeline_label': pipeline.get('label'),
                            'hubspot_id': stage['id'], 'name': stage.get('label'), 'sequence': stage.get('displayOrder', 0),
                            'probability': probability * 100, 'is_closed': closed, 'is_won': closed and probability >= 1}
                    record = existing.get((pipeline['id'], stage['id']))
                    if record:
                        record.write(vals)
                    else:
                        match = crm_stages.filtered(lambda s: s.name.lower() == (stage.get('label') or '').lower())[:1]
                        if not match and vals['is_won']:
                            match = crm_stages.filtered('is_won')[:1]
                        vals['crm_stage_id'] = match.id
                        Stage.create(vals)
        return True

    def action_generate_secret(self):
        """Placeholder secret for local tests of the webhook (use the app client secret in production)."""
        for account in self:
            account.webhook_secret = secrets.token_urlsafe(32)
        return True

    # ------------------------------------------------------------------ synchronization
    def action_sync_now(self):
        self._sync(direction='both')
        return self._notify_done()

    def action_import_now(self):
        self._sync(direction='import')
        return self._notify_done()

    def action_export_now(self):
        self._sync(direction='export')
        return self._notify_done()

    def action_process_queue(self):
        self.env['hubspot.queue'].search([('account_id', 'in', self.ids), ('state', '=', 'pending')])._process()
        return self._notify_done()

    def _notify_done(self):
        failed = sum(self.mapped('failed_count'))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'warning' if failed else 'success', 'title': self.env._('HubSpot'),
            'message': self.env._('Synchronization done. %s failed job(s) in the queue.', failed) if failed
            else self.env._('Synchronization done.'),
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    def _sync(self, direction='both', object_types=None, process=True):
        """Queue the changes of the enabled objects, then process the queue (import first, in dependency order)."""
        for account in self:
            objects = account.object_ids.sorted('sequence')
            if object_types:
                objects = objects.filtered(lambda o: o.object_type in object_types)
            if direction in ('both', 'import'):
                for obj in objects.filtered('import_enabled'):
                    obj._queue_import()
                if process:
                    self.env['hubspot.queue'].search([('account_id', '=', account.id), ('state', '=', 'pending'),
                                                      ('direction', 'in', ('import', 'delete'))])._process()
            if direction in ('both', 'export'):
                for obj in objects.filtered('export_enabled'):
                    obj._queue_export()
                if process:
                    self.env['hubspot.queue'].search([('account_id', '=', account.id), ('state', '=', 'pending'),
                                                      ('direction', '=', 'export')])._process()

    @api.model
    def _cron_sync(self):
        for account in self.search([('auto_sync', '=', True), ('state', '=', 'connected')]):
            try:
                account._sync(direction='both', process=False)
            except HubspotError as error:
                _logger.warning('HubSpot account %s: %s', account.name, error)
                account.write({'last_error': str(error)})
        self.env['hubspot.queue']._cron_process()


class HubspotObject(models.Model):
    _name = 'hubspot.object'
    _description = 'HubSpot object settings'
    _order = 'account_id, sequence'

    account_id = fields.Many2one('hubspot.account', required=True, ondelete='cascade', index=True)
    object_type = fields.Selection(OBJECT_TYPES, required=True)
    sequence = fields.Integer()
    import_enabled = fields.Boolean('Import')
    export_enabled = fields.Boolean('Export')
    last_import = fields.Datetime(help='Last HubSpot modification date imported. Empty = import everything next time.')
    last_export = fields.Datetime(help='Odoo records modified after this date are exported next time.')
    link_count = fields.Integer('Linked records', compute='_compute_link_count')

    _account_object_uniq = models.Constraint('UNIQUE(account_id, object_type)', 'Each object once per account.')

    def _compute_link_count(self):
        counts = {(a.id, t): c for a, t, c in self.env['hubspot.record']._read_group(
            [('account_id', 'in', self.account_id.ids)], ['account_id', 'object_type'], ['__count'])}
        for obj in self:
            obj.link_count = counts.get((obj.account_id.id, obj.object_type), 0)

    def _queue_import(self):
        """Fetch what changed in HubSpot since the last import and queue one job per object."""
        Sync = self.env['hubspot.sync']
        Queue = self.env['hubspot.queue']
        for obj in self:
            account = obj.account_id
            spec = Sync._spec(obj.object_type)
            client = account._client()
            properties = Sync._import_properties(account, obj.object_type)
            log = self.env['hubspot.log'].create({'account_id': account.id, 'direction': 'import',
                                                  'object_type': obj.object_type})
            results = list(client.iter_objects(obj.object_type, properties, spec['modified'], obj.last_import))
            associations = {}
            ids = [r['id'] for r in results]
            for to_type in spec['associations']:
                if ids:
                    associations[to_type] = client.associations(obj.object_type, to_type, ids)
            latest = obj.last_import
            values = []
            Link = self.env['hubspot.record']
            linked = set(Link.search([('account_id', '=', account.id), ('object_type', '=', obj.object_type),
                                      ('hubspot_id', 'in', [str(i) for i in ids])]).mapped('hubspot_id'))
            for result in results:
                updated = from_hubspot_datetime(result.get('updatedAt')) or \
                    from_hubspot_datetime((result.get('properties') or {}).get(spec['modified']))
                if obj.last_import and updated and updated <= obj.last_import and str(result['id']) in linked:
                    continue  # already imported (the search includes the last date again)
                payload = {'id': str(result['id']), 'properties': result.get('properties') or {},
                           'associations': {t: associations[t].get(str(result['id']), []) for t in associations}}
                values.append({'account_id': account.id, 'object_type': obj.object_type, 'direction': 'import',
                               'hubspot_id': str(result['id']), 'payload': payload, 'log_id': log.id})
                if updated and (not latest or updated > latest):
                    latest = updated
            # replace older pending jobs of the same objects (the newest payload wins)
            Queue.search([('account_id', '=', account.id), ('object_type', '=', obj.object_type),
                          ('direction', '=', 'import'), ('state', '=', 'pending'),
                          ('hubspot_id', 'in', [v['hubspot_id'] for v in values])]).write({'state': 'skipped',
                                                                                'error': 'Replaced by a newer job.'})
            Queue.create(values)
            log.write({'queued': len(values), 'date_end': fields.Datetime.now()})
            obj.last_import = latest

    def _queue_export(self):
        """Queue the Odoo records modified since the last export."""
        Sync = self.env['hubspot.sync']
        Queue = self.env['hubspot.queue']
        for obj in self:
            account = obj.account_id
            spec = Sync._spec(obj.object_type)
            start = self.env.cr.now()
            domain = Sync._export_domain(account, obj.object_type)
            if obj.last_export:
                # overlap with the previous run: transactions still open then are caught now (unchanged ones are
                # skipped thanks to the fingerprint)
                domain = domain + [('write_date', '>=', obj.last_export - timedelta(minutes=EXPORT_OVERLAP_MINUTES))]
            records = self.env[spec['model']].with_context(active_test=False).search(domain)
            records = Sync._export_filter(account, obj.object_type, records)
            log = self.env['hubspot.log'].create({'account_id': account.id, 'direction': 'export',
                                                  'object_type': obj.object_type})
            pending = set(Queue.search([('account_id', '=', account.id), ('object_type', '=', obj.object_type),
                                        ('direction', '=', 'export'), ('state', '=', 'pending')]).mapped('res_id'))
            Queue.create([{'account_id': account.id, 'object_type': obj.object_type, 'direction': 'export',
                           'res_model': spec['model'], 'res_id': record.id, 'log_id': log.id}
                          for record in records if record.id not in pending])
            log.write({'queued': len(records), 'date_end': fields.Datetime.now()})
            obj.last_export = start

    def action_import_now(self):
        self.account_id._sync(direction='import', object_types=self.mapped('object_type'))
        return self.account_id._notify_done()

    def action_export_now(self):
        self.account_id._sync(direction='export', object_types=self.mapped('object_type'))
        return self.account_id._notify_done()

    def action_reset(self):
        self.write({'last_import': False, 'last_export': False})
        return True

    def action_view_links(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('hubspot_connector.action_hubspot_record')
        action['domain'] = [('account_id', '=', self.account_id.id), ('object_type', '=', self.object_type)]
        return action


class HubspotDashboard(models.AbstractModel):
    _name = 'hubspot.dashboard'
    _description = 'HubSpot dashboard data'

    @api.model
    def get_dashboard_data(self, account_id=False):
        Account = self.env['hubspot.account']
        accounts = Account.browse(int(account_id)) if account_id else Account.search([])
        Queue = self.env['hubspot.queue']
        base = [('account_id', 'in', accounts.ids)]
        since = fields.Datetime.subtract(fields.Datetime.now(), days=29)
        states = dict(Queue._read_group(base, ['state'], ['__count']))
        done_30 = Queue.search_count(base + [('state', '=', 'done'), ('date_done', '>=', since)])
        links = {t: c for t, c in self.env['hubspot.record']._read_group(base, ['object_type'], ['__count'])}
        objects = []
        for key, label in OBJECT_TYPES:
            lines = accounts.object_ids.filtered(lambda o: o.object_type == key)
            imports = [d for d in lines.mapped('last_import') if d]
            exports = [d for d in lines.mapped('last_export') if d]
            objects.append({
                'key': key, 'label': label, 'linked': links.get(key, 0),
                'import': any(lines.mapped('import_enabled')), 'export': any(lines.mapped('export_enabled')),
                'last_import': fields.Datetime.to_string(max(imports)) if imports else False,
                'last_export': fields.Datetime.to_string(max(exports)) if exports else False,
            })
        daily = {}
        for job in Queue.search_read(base + [('state', '=', 'done'), ('date_done', '>=', since)],
                                     ['date_done', 'direction']):
            day = fields.Date.to_string(fields.Datetime.context_timestamp(self, job['date_done']).date())
            entry = daily.setdefault(day, {'import': 0, 'export': 0})
            entry['export' if job['direction'] == 'export' else 'import'] += 1
        start = fields.Date.context_today(self) - timedelta(days=29)
        days = []
        for offset in range(30):
            day = fields.Date.to_string(start + timedelta(days=offset))
            days.append({'day': day, **daily.get(day, {'import': 0, 'export': 0})})
        logs = self.env['hubspot.log'].search(base + [('queued', '>', 0)], order='date_start desc', limit=8)
        return {
            'accounts': [{'id': a.id, 'name': a.name, 'state': a.state, 'portal_id': a.portal_id or '',
                          'error': a.last_error or '', 'pending': a.pending_count, 'failed': a.failed_count}
                         for a in accounts],
            'all_accounts': [{'id': a.id, 'name': a.name} for a in Account.search([])],
            'queue': {'pending': states.get('pending', 0), 'failed': states.get('failed', 0),
                      'skipped': states.get('skipped', 0), 'done_30': done_30},
            'linked_total': sum(links.values()),
            'objects': objects,
            'days': days,
            'logs': [{'id': log.id, 'date': fields.Datetime.to_string(log.date_start), 'direction': log.direction,
                      'object': dict(OBJECT_TYPES).get(log.object_type, ''), 'queued': log.queued,
                      'created': log.created, 'updated': log.updated, 'failed': log.failed} for log in logs],
        }
