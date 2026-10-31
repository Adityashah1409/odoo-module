from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    short_url_token_style = fields.Selection(related='website_id.short_url_token_style', readonly=False)
    short_url_token_length = fields.Integer(related='website_id.short_url_token_length', readonly=False)
    short_url_validity_days = fields.Integer(related='website_id.short_url_validity_days', readonly=False)

    def action_open_short_urls(self):
        return self.env['ir.actions.act_window']._for_xml_id('short_urls.action_short_url')
