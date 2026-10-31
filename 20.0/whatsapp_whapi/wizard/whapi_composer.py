import base64

from odoo import api, fields, models
from odoo.exceptions import UserError


class WhapiComposer(models.TransientModel):
    _name = 'whapi.composer'
    _description = 'Send by WhatsApp'

    res_model = fields.Char(required=True)
    res_ids = fields.Json(required=True)
    record_count = fields.Integer(compute='_compute_record_count')
    account_id = fields.Many2one('whapi.account', required=True,
                                 default=lambda self: self.env['whapi.account'].search(
                                     [('company_id', 'in', self.env.companies.ids)], limit=1))
    template_id = fields.Many2one('whapi.template', domain="[('model', '=', res_model)]")
    body = fields.Text(compute='_compute_body', store=True, readonly=False)
    attachment_ids = fields.Many2many('ir.attachment', string='Files')
    attach_report = fields.Boolean(compute='_compute_attach_report', store=True, readonly=False)
    has_report = fields.Boolean(compute='_compute_has_report')
    recipient_summary = fields.Text(compute='_compute_recipient_summary')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        context = self.env.context
        template = self.env['whapi.template'].browse(context.get('default_template_id') or [])
        model = context.get('active_model') or template.model
        ids = context.get('active_ids') or ([context['active_id']] if context.get('active_id') else [])
        if model and 'res_model' in fields_list:
            values['res_model'] = model
        if 'res_ids' in fields_list:
            values['res_ids'] = ids
        return values

    @api.depends('res_ids')
    def _compute_record_count(self):
        for wizard in self:
            wizard.record_count = len(wizard.res_ids or [])

    @api.depends('template_id', 'res_ids')
    def _compute_body(self):
        for wizard in self:
            if wizard.template_id and wizard.res_ids:
                rendered = wizard.template_id._whapi_render_body(wizard.res_ids[:1])
                wizard.body = rendered.get(wizard.res_ids[0]) or ''
            elif not wizard.body:
                wizard.body = ''

    @api.depends('template_id')
    def _compute_attach_report(self):
        for wizard in self:
            wizard.attach_report = bool(wizard.template_id.report_id)

    @api.depends('template_id')
    def _compute_has_report(self):
        for wizard in self:
            wizard.has_report = bool(wizard.template_id.report_id)

    def _records(self):
        return self.env[self.res_model].browse(self.res_ids or []).exists()

    @api.model
    def _partner_of(self, record):
        if record._name == 'res.partner':
            return record
        for name in ('partner_id', 'commercial_partner_id', 'customer_id'):
            if name in record._fields and record._fields[name].comodel_name == 'res.partner' and record[name]:
                return record[name]
        return self.env['res.partner']

    @api.depends('res_model', 'res_ids', 'account_id')
    def _compute_recipient_summary(self):
        for wizard in self:
            if not wizard.res_model or not wizard.res_ids:
                wizard.recipient_summary = False
                continue
            lines = []
            for record in wizard._records()[:10]:
                partner = self._partner_of(record)
                phone = partner.phone or self.env._('no phone number')
                lines.append(f'{record.display_name} → {partner.name or "?"} ({phone})')
            if len(wizard.res_ids) > 10:
                lines.append(self.env._('… and %s more', len(wizard.res_ids) - 10))
            wizard.recipient_summary = '\n'.join(lines)

    def action_send(self):
        self.ensure_one()
        records = self._records()
        if not records:
            raise UserError(self.env._('Nothing to send to.'))
        bodies = {}
        if self.template_id and len(records) > 1:
            bodies = self.template_id._whapi_render_body(records.ids)
        sent, skipped = self.env['whapi.message'], []
        for record in records:
            partner = self._partner_of(record)
            chat = partner._whapi_get_chat(self.account_id) if partner else self.env['whapi.chat']
            if not chat:
                skipped.append(record.display_name)
                continue
            attachments = self.env['ir.attachment']
            for attachment in self.attachment_ids:
                attachments |= attachment.copy({'res_model': 'whapi.chat', 'res_id': chat.id})
            if self.attach_report and self.template_id.report_id:
                attachments |= self._render_report(record, chat)
            body = bodies.get(record.id, self.body) if bodies else self.body
            sent |= self.env['whapi.message']._whapi_send_to_chat(chat, body=body, attachments=attachments,
                                                                  record=record)
        failed = sent.filtered(lambda m: m.state == 'failed')
        message = self.env._('%(sent)s WhatsApp message(s) sent.', sent=len(sent - failed))
        if failed:
            message += ' ' + self.env._('%s failed (see WhatsApp › Messages).', len(failed))
        if skipped:
            message += ' ' + self.env._('No phone number for: %s.', ', '.join(skipped[:5]))
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'message': message, 'type': 'warning' if failed or skipped else 'success',
                           'next': {'type': 'ir.actions.act_window_close'}}}

    def _render_report(self, record, chat):
        report = self.template_id.report_id
        content, extension = self.env['ir.actions.report']._render(report.report_name, record.ids)
        name = (record.display_name or 'document').replace('/', '_')
        return self.env['ir.attachment'].create({
            'name': f'{name}.{extension}', 'raw': content,
            'mimetype': 'application/pdf' if extension == 'pdf' else 'application/octet-stream',
            'res_model': 'whapi.chat', 'res_id': chat.id,
        })

    @api.model
    def _b64(self, data):
        return base64.b64encode(data).decode()
