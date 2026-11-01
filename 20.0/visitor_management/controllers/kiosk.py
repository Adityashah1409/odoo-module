from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools import consteq


class VisitorKiosk(http.Controller):

    def _kiosk_company(self, token):
        companies = request.env['res.company'].sudo().search([('visitor_kiosk_token', '=', token)], limit=1)
        if not companies or not token or not consteq(companies.visitor_kiosk_token, token):
            return None
        return companies

    def _render(self, company, template, token, **values):
        values.update(company=company, token=token)
        return request.render(template, values)

    def _kiosk_values(self, company):
        employees = request.env['hr.employee'].sudo().search([
            ('company_id', 'in', [company.id, False]), ('visitor_kiosk_host', '=', True),
        ], order='name')
        types = request.env['visitor.visit.type'].sudo().search([('kiosk', '=', True)])
        return {'hosts': employees, 'visit_types': types}

    @http.route('/visitor/kiosk/<string:token>', type='http', auth='public', methods=['GET'], sitemap=False)
    def kiosk_home(self, token, **kw):
        company = self._kiosk_company(token)
        if not company:
            raise request.not_found()
        return self._render(company, 'visitor_management.kiosk_home', token)

    @http.route('/visitor/kiosk/<string:token>/check-in', type='http', auth='public', methods=['GET', 'POST'],
                sitemap=False)
    def kiosk_check_in(self, token, **post):
        company = self._kiosk_company(token)
        if not company:
            raise request.not_found()
        values = self._kiosk_values(company)
        if request.httprequest.method == 'POST':
            try:
                visit = request.env['visitor.visit'].sudo().with_company(company)._kiosk_check_in(company, post)
            except ValidationError as e:
                values.update(error=e.args[0], post=post)
            else:
                return self._render(company, 'visitor_management.kiosk_welcome', token, visit=visit)
        return self._render(company, 'visitor_management.kiosk_check_in', token, post=values.pop('post', {}),
                            **values)

    @http.route('/visitor/kiosk/<string:token>/check-out', type='http', auth='public', methods=['GET', 'POST'],
                sitemap=False)
    def kiosk_check_out(self, token, **post):
        company = self._kiosk_company(token)
        if not company:
            raise request.not_found()
        values = {}
        if request.httprequest.method == 'POST':
            try:
                visit = request.env['visitor.visit'].sudo()._kiosk_check_out(company, post.get('pass_code'))
            except ValidationError as e:
                values.update(error=e.args[0], post=post)
            else:
                return self._render(company, 'visitor_management.kiosk_goodbye', token, visit=visit)
        return self._render(company, 'visitor_management.kiosk_check_out', token, **values)
