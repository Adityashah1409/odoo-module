from odoo.http import request

from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.web.controllers.home import SIGN_UP_REQUEST_PARAMS

SIGN_UP_REQUEST_PARAMS.update({'first_name', 'last_name'})


class PartnerNamesSignup(AuthSignupHome):

    def get_auth_signup_qcontext(self):
        qcontext = super().get_auth_signup_qcontext()
        if qcontext.get('name') and not (qcontext.get('first_name') or qcontext.get('last_name')):
            parts = request.env['res.partner'].sudo()._partner_names_split(qcontext['name'])
            qcontext['first_name'] = ' '.join(filter(None, [parts['first_name'], parts['middle_name']]))
            qcontext['last_name'] = parts['last_name'] or ''
        return qcontext

    def _prepare_signup_values(self, qcontext, *args, **kwargs):
        first, last = (qcontext.get('first_name') or '').strip(), (qcontext.get('last_name') or '').strip()
        if first or last:
            qcontext['name'] = request.env['res.partner'].sudo()._partner_names_join(first, '', last)
        values = super()._prepare_signup_values(qcontext, *args, **kwargs)
        if first or last:
            values.update({'first_name': first or False, 'last_name': last or False})
        return values
