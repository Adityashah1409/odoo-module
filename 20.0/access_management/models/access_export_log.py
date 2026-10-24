from datetime import timedelta

from odoo import api, fields, models

PARAM = 'access_management.'


class AccessExportLog(models.Model):
    _name = 'access.export.log'
    _description = 'Export log'
    _order = 'id desc'
    _rec_name = 'model'

    user_id = fields.Many2one('res.users', required=True, readonly=True, index=True, ondelete='cascade')
    model = fields.Char(required=True, readonly=True, index=True)
    model_name = fields.Char('Document', readonly=True)
    record_count = fields.Integer('Records', readonly=True)
    field_names = fields.Text('Fields', readonly=True)
    field_count = fields.Integer('Columns', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    ip_address = fields.Char('IP address', readonly=True)
    alert = fields.Boolean('Leak alert', readonly=True, index=True,
                           help='The export was bigger than the alert threshold.')

    @api.model
    def _log_export(self, records, field_names):
        """Log an export; batches of the same export (same user, model and columns, within a minute) are merged."""
        names = [name for name in field_names if name != '.id']
        if not names:
            return self.browse()
        try:
            from odoo.http import request
            ip = request.httprequest.remote_addr if request else False
        except RuntimeError:
            ip = False
        uid = records.env.uid
        text = ', '.join(names)
        recent = self.search([('user_id', '=', uid), ('model', '=', records._name), ('field_names', '=', text),
                              ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=1))], limit=1)
        if recent:
            recent.record_count += len(records)
            log = recent
        else:
            log = self.create({
                'user_id': uid, 'model': records._name,
                'model_name': self.env['ir.model']._get(records._name).name,
                'record_count': len(records), 'field_names': text, 'field_count': len(names),
                'company_id': records.env.company.id, 'ip_address': ip,
            })
        threshold = self.env['ir.config_parameter'].sudo().get_int(PARAM + 'export_alert_threshold')
        if threshold and log.record_count >= threshold and not log.alert:
            log.alert = True
            log._send_alert()
        return log

    def _send_alert(self):
        template = self.env.ref('access_management.mail_template_export_alert', raise_if_not_found=False)
        recipients = (self.env['ir.config_parameter'].sudo().get_str(PARAM + 'alert_emails') or '').strip()
        if template and recipients:
            for log in self:
                template.sudo().send_mail(log.id, email_values={'email_to': recipients})

    @api.model
    def _cron_cleanup(self):
        days = self.env['ir.config_parameter'].sudo().get_int(PARAM + 'export_log_days')
        if days > 0:
            self.search([('create_date', '<', fields.Datetime.now() - timedelta(days=days))]).unlink()
