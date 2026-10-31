import time

import psycopg2

from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _pre_dispatch(cls, rule, args):
        super()._pre_dispatch(rule, args)
        origin = request.session.get('login_as_origin')
        if origin and request.session.uid:
            minutes = request.env['res.users'].sudo()._login_as_minutes()
            if minutes and time.time() - origin.get('time', 0) > minutes * 60:
                if request.env.cr.readonly:
                    # closing the log needs a write: let the request be replayed with a read/write cursor
                    raise psycopg2.errors.ReadOnlySqlTransaction('login as: time limit reached')
                from ..controllers.main import end_login_as  # noqa: PLC0415
                end_login_as('timeout')

    def session_info(self):
        info = super().session_info()
        if request and request.session.uid:
            origin = request.session.get('login_as_origin')
            Users = self.env['res.users']
            minutes = Users.sudo()._login_as_minutes()
            info['login_as'] = {
                'origin': origin and {'id': origin['uid'], 'name': origin['name']},
                'can': Users._login_as_allowed_for(origin['uid'] if origin else request.session.uid),
                'remaining': origin and minutes and max(int(origin.get('time', 0) + minutes * 60 - time.time()), 0),
            }
        return info
