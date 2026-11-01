from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize
from odoo.tools.mail import email_split_and_format


def split_emails(*values):
    """ Unique formatted e-mails from comma separated strings, in order. """
    seen, result = set(), []
    for value in values:
        for email in email_split_and_format(value or ''):
            key = email_normalize(email) or email
            if key not in seen:
                seen.add(key)
                result.append(email)
    return result


def check_emails(env, *values):
    for value in values:
        for email in email_split_and_format(value or ''):
            if not email_normalize(email):
                raise ValidationError(env._('"%s" is not a valid e-mail address.', email))
        if value and value.strip() and not email_split_and_format(value):
            raise ValidationError(env._('"%s" is not a valid e-mail address.', value))


class MailCcRule(models.Model):
    _name = 'mail.cc.rule'
    _description = 'Cc / Bcc rule for e-mails'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, help='Empty: all companies.')
    model_ids = fields.Many2many('ir.model', string='Documents', domain=[('is_mail_thread', '=', True)],
                                 help='Empty: all documents.')
    user_ids = fields.Many2many('res.users', string='Senders', domain=[('share', '=', False)],
                                help='Empty: everybody.')
    group_ids = fields.Many2many('res.groups', string='Sender groups',
                                 help='The sender must belong to one of these groups. Empty: everybody.')
    email_cc = fields.Char('Cc')
    email_bcc = fields.Char('Bcc')
    reply_to = fields.Char('Reply-To', help='Used when no previous rule gives a Reply-To.')

    @api.constrains('name', 'email_cc', 'email_bcc', 'reply_to')
    def _check_addresses(self):
        for rule in self:
            check_emails(self.env, rule.email_cc, rule.email_bcc, rule.reply_to)
            if not (rule.email_cc or rule.email_bcc or rule.reply_to):
                raise ValidationError(self.env._('Give at least a Cc, a Bcc or a Reply-To.'))

    def _applies(self, model, user):
        self.ensure_one()
        if self.model_ids and model not in self.model_ids.mapped('model'):
            return False
        if self.user_ids and user not in self.user_ids:
            return False
        if self.group_ids and not (self.group_ids & user.all_group_ids):
            return False
        return True

    @api.model
    def _get_defaults(self, model, user=None, company=None):
        """ {'cc': [...], 'bcc': [...], 'reply_to': str} for an e-mail written by ``user`` on ``model``. """
        user = user or self.env.user
        company = company or self.env.company
        rules = self.sudo().search([('company_id', 'in', [company.id, False])]).filtered(
            lambda r: r._applies(model, user))
        cc = split_emails(company.mail_default_cc, *rules.mapped('email_cc'))
        bcc = split_emails(company.mail_default_bcc, *rules.mapped('email_bcc'))
        bcc = [e for e in bcc if email_normalize(e) not in {email_normalize(c) for c in cc}]
        reply_to = next((r.reply_to for r in rules if r.reply_to), False) or company.mail_default_reply_to or False
        return {'cc': cc, 'bcc': bcc, 'reply_to': reply_to}
