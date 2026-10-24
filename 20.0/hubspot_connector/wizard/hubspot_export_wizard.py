from odoo import api, fields, models
from odoo.exceptions import UserError

MODEL_OBJECTS = {
    'product.template': ['products'], 'crm.lead': ['deals'], 'sale.order': ['quotes'], 'account.move': ['invoices'],
}


class HubspotExportWizard(models.TransientModel):
    _name = 'hubspot.export.wizard'
    _description = 'Export records to HubSpot'

    account_id = fields.Many2one('hubspot.account', required=True, domain=[('state', '=', 'connected')],
                                 default=lambda self: self.env['hubspot.account'].search([('state', '=', 'connected')],
                                                                                          limit=1))
    res_model = fields.Char(required=True, default=lambda self: self.env.context.get('active_model'))
    res_ids = fields.Json(default=lambda self: self.env.context.get('active_ids') or [])
    record_count = fields.Integer(compute='_compute_record_count')
    process_now = fields.Boolean('Send now', default=True, help='Otherwise the records wait for the next scheduled run.')

    @api.depends('res_ids')
    def _compute_record_count(self):
        for wizard in self:
            wizard.record_count = len(wizard.res_ids or [])

    def _object_type(self, record):
        if record._name == 'res.partner':
            link = self.env['hubspot.record'].search([('account_id', '=', self.account_id.id),
                                                      ('object_type', '=', 'companies'),
                                                      ('res_model', '=', 'res.partner'), ('res_id', '=', record.id)])
            return 'companies' if link or record.is_company or record.child_ids else 'contacts'
        return MODEL_OBJECTS[record._name][0]

    def action_export(self):
        self.ensure_one()
        if self.res_model not in MODEL_OBJECTS and self.res_model != 'res.partner':
            raise UserError(self.env._('These records cannot be exported to HubSpot.'))
        records = self.env[self.res_model].browse(self.res_ids).exists()
        if not records:
            raise UserError(self.env._('Select at least one record.'))
        log = self.env['hubspot.log'].create({'account_id': self.account_id.id, 'direction': 'export',
                                              'queued': len(records)})
        jobs = self.env['hubspot.queue'].create([{
            'account_id': self.account_id.id, 'object_type': self._object_type(record), 'direction': 'export',
            'res_model': record._name, 'res_id': record.id, 'log_id': log.id} for record in records])
        if self.process_now:
            jobs._process()
        failed = jobs.filtered(lambda j: j.state == 'failed' or (j.state == 'pending' and j.error))
        message = self.env._('%(done)s record(s) exported, %(failed)s with errors (see Queue).',
                             done=len(jobs) - len(failed), failed=len(failed)) if self.process_now else \
            self.env._('%s record(s) queued for the next synchronization.', len(jobs))
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'warning' if failed else 'success', 'title': self.env._('HubSpot'), 'message': message,
            'next': {'type': 'ir.actions.act_window_close'}}}
