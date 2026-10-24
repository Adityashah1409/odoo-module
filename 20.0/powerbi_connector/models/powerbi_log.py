from odoo import api, fields, models


class PowerBILog(models.Model):
    _name = 'powerbi.log'
    _description = 'Power BI Sync Log'
    _order = 'id desc'

    dataset_id = fields.Many2one('powerbi.dataset', ondelete='cascade', index=True)
    table_id = fields.Many2one('powerbi.table', ondelete='set null')
    operation = fields.Char(required=True)
    status = fields.Selection([('success', 'Success'), ('error', 'Error')], default='success', required=True)
    rows = fields.Integer()
    duration = fields.Float("Duration (s)", digits=(8, 2))
    message = fields.Text()

    @api.autovacuum
    def _gc_old(self):
        self.search([('create_date', '<', fields.Datetime.subtract(fields.Datetime.now(), days=90))]).unlink()
