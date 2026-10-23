from odoo import api, fields, models


class CloudStorageLog(models.Model):
    _name = 'cloud.storage.log'
    _description = 'Cloud Storage Sync Log'
    _order = 'id desc'

    client_id = fields.Many2one('cloud.storage.client', ondelete='cascade', index=True)
    level = fields.Selection([('info', 'Info'), ('warning', 'Warning'), ('error', 'Error')],
                             default='info', required=True)
    message = fields.Text(required=True)
    folder_id = fields.Many2one('cloud.storage.folder', ondelete='set null')
    attachment_id = fields.Many2one('ir.attachment', ondelete='set null')

    @api.autovacuum
    def _gc_old_logs(self):
        days = int(self.env['ir.config_parameter'].sudo().get_str('cloud_storage_sync.log_retention_days', 30))
        self.search([('create_date', '<', fields.Datetime.subtract(fields.Datetime.now(), days=days))]).unlink()
