import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .hubspot_account import OBJECT_TYPES
from .hubspot_client import HubspotError, HubspotSkip

_logger = logging.getLogger(__name__)


class HubspotQueue(models.Model):
    _name = 'hubspot.queue'
    _description = 'HubSpot synchronization job'
    _order = 'id'

    account_id = fields.Many2one('hubspot.account', required=True, ondelete='cascade', index=True)
    log_id = fields.Many2one('hubspot.log', ondelete='set null', index=True)
    object_type = fields.Selection(OBJECT_TYPES, required=True, index=True)
    direction = fields.Selection([('import', 'Import'), ('export', 'Export'), ('delete', 'Deletion in HubSpot')],
                                 required=True, index=True)
    hubspot_id = fields.Char('HubSpot ID', index=True)
    res_model = fields.Char()
    res_id = fields.Many2oneReference('Odoo record', model_field='res_model')
    record_name = fields.Char(compute='_compute_record_name')
    payload = fields.Json(help='HubSpot object as received (empty: it is read from HubSpot when processed).')
    state = fields.Selection([('pending', 'Pending'), ('done', 'Done'), ('failed', 'Failed'), ('skipped', 'Skipped')],
                             default='pending', required=True, index=True)
    result = fields.Selection([('created', 'Created'), ('updated', 'Updated'), ('unchanged', 'Unchanged'),
                               ('archived', 'Archived')], readonly=True)
    attempts = fields.Integer(readonly=True)
    error = fields.Text(readonly=True)
    date_done = fields.Datetime(readonly=True)

    @api.depends('direction', 'object_type', 'hubspot_id')
    def _compute_display_name(self):
        directions = dict(self._fields['direction']._description_selection(self.env))
        objects = dict(self._fields['object_type']._description_selection(self.env))
        for job in self:
            job.display_name = ' '.join(filter(None, [
                directions.get(job.direction), objects.get(job.object_type),
                job.hubspot_id and f'#{job.hubspot_id}' or job.record_name]))

    def _compute_record_name(self):
        for job in self:
            record = job._record()
            job.record_name = record.display_name if record else False

    def _record(self):
        self.ensure_one()
        if self.res_model and self.res_id and self.res_model in self.env:
            return self.env[self.res_model].with_context(active_test=False).browse(self.res_id).exists()
        return False

    def _process(self):
        """Run the jobs one by one; a failing job is rolled back alone and retried on the next run."""
        Sync = self.env['hubspot.sync']
        done = 0
        for job in self.filtered(lambda j: j.state == 'pending').sorted('id'):
            account = job.account_id
            try:
                with self.env.cr.savepoint():
                    if job.direction == 'import':
                        record, result = Sync._import_job(job)
                    elif job.direction == 'delete':
                        record, result = Sync._delete_job(job)
                    else:
                        record, result = Sync._export_job(job)
                job.write({'state': 'done', 'result': result, 'error': False, 'date_done': fields.Datetime.now(),
                           'attempts': job.attempts + 1,
                           **({'res_model': record._name, 'res_id': record.id} if record else {})})
            except HubspotSkip as skip:
                job.write({'state': 'skipped', 'error': str(skip), 'attempts': job.attempts + 1,
                           'date_done': fields.Datetime.now()})
            except (HubspotError, UserError, ValidationError, AccessError, ValueError, KeyError) as error:
                attempts = job.attempts + 1
                message = str(error) if not isinstance(error, KeyError) else f'Missing value: {error}'
                job.write({'attempts': attempts, 'error': message,
                           'state': 'failed' if attempts >= max(account.max_attempts, 1) else 'pending'})
                _logger.info('HubSpot job %s (%s %s) failed: %s', job.id, job.direction, job.object_type, message)
            done += 1
        return done

    @api.model
    def _cron_process(self):
        for account in self.env['hubspot.account'].search([('state', '=', 'connected')]):
            jobs = self.search([('account_id', '=', account.id), ('state', '=', 'pending')],
                               limit=max(account.batch_size, 1))
            # imports before exports so that associations can be resolved
            jobs = jobs.sorted(lambda j: (j.direction == 'export', j.id))
            jobs._process()
            if self.env.context.get('ir_cron_progress_id'):
                # inside the scheduled action: commit what is done for this account
                self.env['ir.cron']._commit_progress(len(jobs))

    def action_retry(self):
        self.filtered(lambda j: j.state in ('failed', 'skipped')).write({'state': 'pending', 'attempts': 0})
        self.filtered(lambda j: j.state == 'pending')._process()
        return True

    def action_open_record(self):
        self.ensure_one()
        record = self._record()
        if not record:
            raise UserError(self.env._('There is no Odoo record for this job.'))
        return {'type': 'ir.actions.act_window', 'res_model': record._name, 'res_id': record.id,
                'views': [(False, 'form')], 'target': 'current'}
