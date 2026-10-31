from odoo import api, fields, models


class WhapiTemplate(models.Model):
    _name = 'whapi.template'
    _description = 'WhatsApp message template'
    _inherit = ['mail.render.mixin']
    _order = 'sequence, name, id'

    _unrestricted_rendering = True

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one('ir.model', string='Applies to', required=True, ondelete='cascade',
                               domain=[('transient', '=', False)],
                               default=lambda self: self.env['ir.model']._get('res.partner'))
    model = fields.Char(related='model_id.model', store=True, index=True)
    body = fields.Text(required=True, translate=True,
                       help='Text of the message. Use {{ object.name }} to insert values of the document.')
    report_id = fields.Many2one('ir.actions.report', string='Attach report',
                                domain="[('model', '=', model), ('report_type', '=', 'qweb-pdf')]",
                                help='PDF of the document sent with the message.')
    attachment_ids = fields.Many2many('ir.attachment', string='Files')
    binding_action_id = fields.Many2one('ir.actions.act_window', readonly=True, copy=False)
    company_id = fields.Many2one('res.company')

    @api.depends('model')
    def _compute_render_model(self):
        for template in self:
            template.render_model = template.model

    def action_add_binding(self):
        view = self.env.ref('whatsapp_whapi.whapi_composer_view_form')
        for template in self.filtered(lambda t: not t.binding_action_id):
            template.binding_action_id = self.env['ir.actions.act_window'].sudo().create({
                'name': self.env._('WhatsApp: %s', template.name),
                'res_model': 'whapi.composer',
                'view_mode': 'form',
                'view_id': view.id,
                'target': 'new',
                'context': f"{{'default_template_id': {template.id}}}",
                'binding_model_id': template.model_id.id,
                'binding_view_types': 'form,list',
                'group_ids': [(6, 0, [self.env.ref('whatsapp_whapi.group_whapi_user').id])],
            })

    def action_remove_binding(self):
        self.binding_action_id.sudo().unlink()

    def unlink(self):
        self.binding_action_id.sudo().unlink()
        return super().unlink()

    def _whapi_render_body(self, res_ids):
        self.ensure_one()
        return self._render_field('body', res_ids)
