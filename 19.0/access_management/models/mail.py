from odoo import api, models
from odoo.http import request


def _from_chatter():
    """True when the current request comes from the chatter composer."""
    try:
        return bool(request) and request.httprequest.path.startswith('/mail/message/post')
    except RuntimeError:
        return False


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def message_post(self, **kwargs):
        if kwargs.get('message_type', 'notification') == 'comment' and _from_chatter() and self.env.uid != 1:
            # the chatter route posts in sudo: check the restrictions of the user behind the request
            restrictions = self.env['access.rule']._restrictions_for(self.env.uid, self.env.company.id)
            info = restrictions and restrictions['models'].get(self._name)
            if info:
                note = kwargs.get('subtype_xmlid') == 'mail.mt_note' or \
                    kwargs.get('subtype_id') == self.env['ir.model.data']._xmlid_to_res_id('mail.mt_note')
                if info.get('hide_chatter') or (note and info.get('hide_log_note')) or \
                        (not note and info.get('hide_send_message')):
                    self._am_raise(self.env._('You cannot post messages on these records.'))
        return super().message_post(**kwargs)


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            Rule = self.env['access.rule']
            for vals in vals_list:
                model = vals.get('res_model') or (
                    self.env['ir.model'].sudo().browse(vals['res_model_id']).model if vals.get('res_model_id') else None)
                info = model and Rule._model_restrictions(model)
                if info and (info.get('hide_activities') or info.get('hide_chatter')):
                    self.env['base']._am_raise(self.env._('You cannot schedule activities on these records.'))
        return super().create(vals_list)
