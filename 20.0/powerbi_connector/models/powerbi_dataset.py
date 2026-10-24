import re
import secrets
import time
from datetime import date, datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext
from odoo.tools.safe_eval import safe_eval

from .powerbi_connection import PowerBIError

PUSH_BATCH = 10000  # Power BI accepts at most 10,000 rows per POST
FIELD_TYPES = {
    'integer': 'Int64', 'many2one': 'Int64', 'float': 'Double', 'monetary': 'Double',
    'boolean': 'Boolean', 'date': 'Datetime', 'datetime': 'Datetime',
    'char': 'String', 'text': 'String', 'html': 'String', 'selection': 'String',
}
EXPORTABLE = tuple(FIELD_TYPES)


def to_powerbi(field, value, record):
    """Odoo value -> JSON value for Power BI."""
    if field.type == 'many2one':
        return value.id or None
    if value is False or value is None:
        return None if field.type != 'boolean' else False
    if field.type == 'datetime' and isinstance(value, datetime):
        return value.strftime('%Y-%m-%dT%H:%M:%SZ')
    if field.type == 'date' and isinstance(value, date):
        return value.strftime('%Y-%m-%dT00:00:00Z')
    if field.type == 'selection':
        return dict(field._description_selection(record.env)).get(value, value)
    if field.type == 'html':
        return html2plaintext(value or '')
    if field.type in ('char', 'text') and not isinstance(value, str):
        return str(value)
    return value


class PowerBIDataset(models.Model):
    _name = 'powerbi.dataset'
    _description = 'Power BI Dataset'
    _order = 'name'

    name = fields.Char(required=True, help="Dataset name in Power BI.")
    active = fields.Boolean(default=True)
    mode = fields.Selection(
        [('push', 'Push to Power BI (REST API)'), ('feed', 'JSON feed (Power BI pulls it)')],
        default='push', required=True)
    connection_id = fields.Many2one('powerbi.connection', ondelete='restrict')
    powerbi_dataset_id = fields.Char("Power BI dataset ID", readonly=True, copy=False)
    state = fields.Selection([('draft', 'Draft'), ('published', 'Published'), ('error', 'Error')],
                             default='draft', required=True, readonly=True, copy=False)
    table_ids = fields.One2many('powerbi.table', 'dataset_id', copy=True)
    user_id = fields.Many2one('res.users', string="Read data as", required=True, default=lambda self: self.env.user,
                              help="Records are read with this user's access rights.")
    access_key = fields.Char(readonly=True, copy=False, groups='powerbi_connector.group_powerbi_manager',
                             default=lambda self: secrets.token_urlsafe(32))
    feed_url = fields.Char(compute='_compute_feed_url')
    auto_push = fields.Boolean("Scheduled push", help="Push this dataset automatically.")
    push_interval = fields.Integer("Every (hours)", default=24)
    next_push = fields.Datetime(copy=False)
    last_push = fields.Datetime(readonly=True, copy=False)
    log_ids = fields.One2many('powerbi.log', 'dataset_id')
    relationship_info = fields.Text(compute='_compute_relationship_info', string="Relationships")

    @api.constrains('mode', 'connection_id')
    def _check_connection(self):
        for dataset in self:
            if dataset.mode == 'push' and not dataset.connection_id:
                raise ValidationError(_("Push datasets need a Power BI connection."))

    def _compute_feed_url(self):
        base = self.env['ir.config_parameter'].sudo().get_str('web.base.url', '')
        for dataset in self:
            dataset.feed_url = f"{base}/powerbi/feed/{dataset.id}" if dataset.id else False

    @api.depends('table_ids.column_ids.field_id', 'table_ids.model_id')
    def _compute_relationship_info(self):
        for dataset in self:
            dataset.relationship_info = '\n'.join(
                f"{r['fromTable']}.{r['fromColumn']} → {r['toTable']}.{r['toColumn']}"
                for r in dataset._relationships()) or False

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------
    def _relationships(self):
        """Many2one columns pointing to the model of another table of the dataset."""
        self.ensure_one()
        tables_by_model = {t.model_id.model: t for t in self.table_ids}
        relations = []
        for table in self.table_ids:
            for column in table.column_ids.filtered(lambda c: c.field_id.ttype == 'many2one'):
                target = tables_by_model.get(column.field_id.relation)
                if target:
                    relations.append({
                        'name': f"{table.name}_{column.name}",
                        'fromTable': table.name, 'fromColumn': column.name,
                        'toTable': target.name, 'toColumn': 'id',
                        'crossFilteringBehavior': 'OneDirection',
                    })
        return relations

    def _schema(self):
        self.ensure_one()
        return {
            'name': self.name,
            'defaultMode': 'Push',
            'tables': [table._schema() for table in self.table_ids],
            'relationships': self._relationships(),
        }

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_publish(self):
        """Create the dataset in Power BI, or update the schema of its tables."""
        for dataset in self.filtered(lambda d: d.mode == 'push'):
            started = time.monotonic()
            try:
                if dataset.powerbi_dataset_id:
                    for table in dataset.table_ids:
                        dataset.connection_id._api(
                            'PUT', f"datasets/{dataset.powerbi_dataset_id}/tables/{table.name}", table._schema())
                    message = _("Schema of %s table(s) updated.", len(dataset.table_ids))
                else:
                    result = dataset.connection_id._api('POST', 'datasets?defaultRetentionPolicy=basicFIFO',
                                                        dataset._schema())
                    dataset.powerbi_dataset_id = result['id']
                    message = _("Dataset created in Power BI.")
                dataset.state = 'published'
                dataset._log('publish', message, started=started)
            except PowerBIError as e:
                dataset.state = 'error'
                dataset._log('publish', str(e), status='error', started=started)
        return True

    def action_push(self, incremental=False):
        """Send the rows of every table (full refresh, or new records only)."""
        for dataset in self.filtered(lambda d: d.mode == 'push'):
            if not dataset.powerbi_dataset_id:
                dataset.action_publish()
                if dataset.state == 'error':
                    continue
            for table in dataset.table_ids:
                table._push(incremental=incremental)
            dataset.write({'last_push': fields.Datetime.now(),
                           'next_push': fields.Datetime.now() + timedelta(hours=dataset.push_interval or 24)})
        return True

    def action_push_incremental(self):
        return self.action_push(incremental=True)

    def action_regenerate_key(self):
        for dataset in self:
            dataset.access_key = secrets.token_urlsafe(32)

    def action_view_logs(self):
        action = self.env['ir.actions.act_window']._for_xml_id('powerbi_connector.action_powerbi_log')
        action['domain'] = [('dataset_id', '=', self.id)]
        return action

    def _log(self, operation, message, status='success', rows=0, table=None, started=None):
        self.env['powerbi.log'].sudo().create({
            'dataset_id': self.id, 'table_id': table.id if table else False, 'operation': operation,
            'status': status, 'rows': rows, 'message': message,
            'duration': (time.monotonic() - started) if started else 0.0,
        })

    @api.model
    def _cron_push(self):
        now = fields.Datetime.now()
        datasets = self.search([('mode', '=', 'push'), ('auto_push', '=', True),
                                '|', ('next_push', '=', False), ('next_push', '<=', now)])
        datasets.action_push()


class PowerBITable(models.Model):
    _name = 'powerbi.table'
    _description = 'Power BI Table'
    _order = 'sequence, id'

    name = fields.Char(required=True, help="Table name in Power BI (letters, digits and underscores).")
    sequence = fields.Integer(default=10)
    dataset_id = fields.Many2one('powerbi.dataset', required=True, ondelete='cascade', index=True)
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade', domain=[('transient', '=', False)])
    model_name = fields.Char(related='model_id.model', string="Model name")
    domain = fields.Char(default='[]', required=True)
    row_limit = fields.Integer(help="0 = all records.")
    column_ids = fields.One2many('powerbi.column', 'table_id', copy=True)
    last_sync_date = fields.Datetime(readonly=True, copy=False,
                                     help="Records created after this date are sent by an incremental push.")
    record_count = fields.Integer(compute='_compute_record_count', string="Records")

    _name_uniq = models.Constraint('UNIQUE(dataset_id, name)', "Table names must be unique in a dataset.")

    @api.constrains('name')
    def _check_name(self):
        for table in self:
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', table.name or ''):
                raise ValidationError(_("Table name %s: use letters, digits and underscores only.", table.name))

    @api.constrains('domain', 'model_id')
    def _check_domain(self):
        for table in self:
            try:
                self.env[table.model_name].search_count(safe_eval(table.domain or '[]'), limit=1)
            except Exception as e:  # noqa: BLE001
                raise ValidationError(_("Invalid filter on table %(table)s: %(error)s", table=table.name, error=e)) from e

    @api.onchange('model_id')
    def _onchange_model_id(self):
        if self.model_id and not self.name:
            self.name = re.sub(r'[^A-Za-z0-9_]', '_', self.model_id.model.title().replace('.', ''))

    def _compute_record_count(self):
        for table in self:
            try:
                table.record_count = self.env[table.model_name].search_count(safe_eval(table.domain or '[]'))
            except Exception:  # noqa: BLE001
                table.record_count = 0

    def _schema(self):
        self.ensure_one()
        columns = [{'name': 'id', 'dataType': 'Int64'}]
        columns += [{'name': c.name, 'dataType': c.data_type} for c in self.column_ids if c.name != 'id']
        return {'name': self.name, 'columns': columns}

    def _records(self, incremental=False):
        self.ensure_one()
        Model = self.env[self.model_name].with_user(self.dataset_id.user_id)
        domain = safe_eval(self.domain or '[]')
        if incremental and self.last_sync_date:
            domain = domain + [('create_date', '>', self.last_sync_date)]
        return Model.search(domain, order='id', limit=self.row_limit or None)

    def _rows(self, records):
        """Rows as dicts: id + one key per column."""
        self.ensure_one()
        columns = [(c.name, records._fields[c.field_id.name]) for c in self.column_ids if c.name != 'id']
        rows = []
        for record in records:
            row = {'id': record.id}
            for name, field in columns:
                row[name] = to_powerbi(field, record[field.name], record)
            rows.append(row)
        return rows

    def _push(self, incremental=False):
        self.ensure_one()
        dataset = self.dataset_id
        connection = dataset.connection_id
        path = f"datasets/{dataset.powerbi_dataset_id}/tables/{self.name}/rows"
        started = time.monotonic()
        # same clock as create_date (transaction start): records created by transactions that start
        # after this push are picked up by the next incremental push
        sync_started = self.env.cr.now()
        try:
            records = self._records(incremental=incremental)
            if not incremental or not self.last_sync_date:
                connection._api('DELETE', path)
            sent = 0
            for start in range(0, len(records), PUSH_BATCH):
                rows = self._rows(records[start:start + PUSH_BATCH])
                connection._api('POST', path, {'rows': rows})
                sent += len(rows)
            self.last_sync_date = sync_started
            dataset._log('push_incremental' if incremental else 'push_full',
                         _("%(rows)s row(s) sent to %(table)s.", rows=sent, table=self.name),
                         rows=sent, table=self, started=started)
            return sent
        except PowerBIError as e:
            dataset.state = 'error'
            dataset._log('push', str(e), status='error', table=self, started=started)
            return 0

    def action_preview(self):
        self.ensure_one()
        rows = self._rows(self._records()[:20])
        if not rows:
            raise UserError(_("No record matches this table."))
        header = list(rows[0])
        lines = [' | '.join(header)] + [' | '.join(str(row[h]) for h in header) for row in rows]
        raise UserError(_("First rows of %(table)s:\n\n%(rows)s", table=self.name, rows='\n'.join(lines)))


class PowerBIColumn(models.Model):
    _name = 'powerbi.column'
    _description = 'Power BI Column'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    table_id = fields.Many2one('powerbi.table', required=True, ondelete='cascade', index=True)
    model_id = fields.Many2one(related='table_id.model_id')
    field_id = fields.Many2one('ir.model.fields', required=True, ondelete='cascade',
                               domain="[('model_id', '=', model_id), ('ttype', 'in', %s), ('store', '=', True)]"
                                      % (list(EXPORTABLE),))
    name = fields.Char(compute='_compute_name', store=True, readonly=False, required=True, precompute=True)
    data_type = fields.Char(compute='_compute_data_type', store=True, precompute=True)

    @api.depends('field_id')
    def _compute_name(self):
        for column in self:
            if column.field_id and not column.name:
                column.name = column.field_id.name

    @api.depends('field_id.ttype')
    def _compute_data_type(self):
        for column in self:
            column.data_type = FIELD_TYPES.get(column.field_id.ttype, 'String')
