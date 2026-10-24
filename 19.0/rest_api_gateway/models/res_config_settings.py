from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rest_api_log_bodies = fields.Boolean(
        'Log request and response bodies', config_parameter='rest_api_gateway.log_bodies')
    rest_api_log_days = fields.Integer(
        'Keep logs (days)', config_parameter='rest_api_gateway.log_days', default=30)
    rest_api_rate_limit = fields.Integer(
        'Requests per minute', config_parameter='rest_api_gateway.rate_limit', default=0,
        help='Per user and IP address. 0 = no limit.')
    rest_api_max_limit = fields.Integer(
        'Maximum page size', config_parameter='rest_api_gateway.max_limit', default=1000)
    rest_api_cors_origins = fields.Char(
        'CORS origins', config_parameter='rest_api_gateway.cors_origins',
        help='Comma-separated origins allowed to call the API from a browser, or * for any.')
    rest_api_docs_public = fields.Boolean(
        'Public documentation', config_parameter='rest_api_gateway.docs_public',
        help='When off, /api/docs and the OpenAPI file need an Odoo login.')
    rest_api_doc_models = fields.Char(
        'Documented models', config_parameter='rest_api_gateway.doc_models', default='res.partner',
        help='Comma-separated models whose fields are described in the OpenAPI file.')
