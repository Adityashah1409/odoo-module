import hashlib
import hmac
import os
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


def hash_pin(pin, salt=None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac('sha256', pin.encode(), bytes.fromhex(salt), 120_000).hex()
    return f'pbkdf2${salt}${digest}'


def verify_pin(pin, stored):
    try:
        _algo, salt, digest = stored.split('$')
    except (AttributeError, ValueError):
        return False
    return hmac.compare_digest(hash_pin(pin, salt).split('$')[2], digest)


class AccessMenuLock(models.Model):
    _name = 'access.menu.lock'
    _description = 'PIN-protected menu'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(compute='_compute_name', store=True, readonly=False)
    active = fields.Boolean(default=True)
    menu_id = fields.Many2one('ir.ui.menu', string='Menu', required=True, ondelete='cascade',
                              domain="[('action', '!=', False)]", tracking=True,
                              help='The menu (and its action) asks for the code. Submenus of a parent menu are '
                                   'protected one by one.')
    action_ref = fields.Char(compute='_compute_action_ref', store=True, index=True)
    pin_type = fields.Selection([('pin', 'Numeric PIN'), ('passphrase', 'Passphrase')], default='pin',
                                required=True, string='Code type')
    code = fields.Char('New code', compute='_compute_code', inverse='_inverse_code', copy=False,
                       help='Write a new code to set it. It is stored hashed and never shown again.')
    code_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    has_code = fields.Boolean(compute='_compute_has_code')
    user_ids = fields.Many2many('res.users', string='Only for users', domain="[('share', '=', False)]")
    group_ids = fields.Many2many('res.groups', string='Only for groups')
    max_attempts = fields.Integer('Attempts before lockout', default=3)
    lockout_minutes = fields.Integer('Lockout (minutes)', default=15)
    unlock_minutes = fields.Integer('Stays unlocked (minutes)', default=30,
                                    help='How long the menu stays open in the browser session after a good code.')
    alert_emails = fields.Char('Alert e-mails', help='Comma-separated. Told when a user is locked out.')
    attempt_ids = fields.One2many('access.lock.attempt', 'lock_id', string='Attempts')
    failed_count = fields.Integer(compute='_compute_failed_count', string='Failed (7 days)')

    @api.depends('menu_id')
    def _compute_name(self):
        for lock in self:
            lock.name = lock.menu_id.complete_name or lock.name

    @api.depends('menu_id.action')
    def _compute_action_ref(self):
        for lock in self:
            action = lock.menu_id.action
            lock.action_ref = f'{action._name},{action.id}' if action else False

    def _compute_code(self):
        self.code = False

    def _inverse_code(self):
        for lock in self.filtered('code'):
            lock._set_code(lock.code)

    def _compute_has_code(self):
        for lock in self:
            lock.has_code = bool(lock.sudo().code_hash)

    def _compute_failed_count(self):
        since = fields.Datetime.now() - timedelta(days=7)
        data = dict(self.env['access.lock.attempt']._read_group(
            [('lock_id', 'in', self.ids), ('success', '=', False), ('create_date', '>=', since)],
            ['lock_id'], ['__count']))
        for lock in self:
            lock.failed_count = data.get(lock, 0)

    @api.model_create_multi
    def create(self, vals_list):
        locks = super().create(vals_list)
        locks._check_code_set()
        return locks

    def _set_code(self, code):
        code = code.strip()
        for lock in self:
            if lock.pin_type == 'pin' and (not code.isdigit() or len(code) < 4):
                raise ValidationError(self.env._('A PIN has at least 4 digits.'))
            if lock.pin_type == 'passphrase' and len(code) < 6:
                raise ValidationError(self.env._('A passphrase has at least 6 characters.'))
            lock.sudo().code_hash = hash_pin(code)
            lock.message_post(body=self.env._('The code was changed.'))

    def _check_code_set(self):
        for lock in self:
            if not lock.sudo().code_hash:
                raise ValidationError(self.env._('Set a code for %s.', lock.menu_id.display_name))

    def _applies_to(self, user):
        self.ensure_one()
        if not self.user_ids and not self.group_ids:
            return True
        return user in self.user_ids or bool(self.group_ids & user.all_group_ids)

    @api.model
    def _lock_for_action(self, action):
        """Active lock of ``action`` that applies to the current user, if any."""
        if self.env.su or not action:
            return self.browse()
        ref = f'{action._name},{action.id}'
        locks = self.sudo().search([('action_ref', '=', ref)])
        user = self.env.user
        return locks.filtered(lambda l: l._applies_to(user))[:1]

    def _recent_failures(self, user):
        """Wrong codes of ``user`` since the last good one, within the lockout window (newest first)."""
        self.ensure_one()
        since = fields.Datetime.now() - timedelta(minutes=self.lockout_minutes)
        attempts = self.env['access.lock.attempt'].sudo().search(
            [('lock_id', '=', self.id), ('user_id', '=', user.id), ('create_date', '>=', since)],
            order='id desc')
        failures = []
        for attempt in attempts:
            if attempt.success:
                break
            failures.append(attempt)
        return failures

    def _locked_until(self, user):
        """End of the lockout of ``user`` (naive UTC) or False."""
        self.ensure_one()
        failures = self._recent_failures(user)
        if self.max_attempts and len(failures) >= self.max_attempts:
            return failures[0].create_date + timedelta(minutes=self.lockout_minutes)
        return False

    def _try_unlock(self, user, code, ip=False):
        """Check ``code`` for ``user``; return (ok, message)."""
        self.ensure_one()
        lock = self.sudo()
        until = lock._locked_until(user)
        if until:
            return False, self.env._('Too many wrong codes. Try again after %s (UTC).',
                                     fields.Datetime.to_string(until)[11:16])
        ok = verify_pin((code or '').strip(), lock.code_hash)
        Attempt = self.env['access.lock.attempt'].sudo()
        Attempt.create({'lock_id': lock.id, 'user_id': user.id, 'success': ok, 'ip_address': ip})
        if ok:
            return True, ''
        if lock._locked_until(user):
            lock._send_lockout_alert(user)
            return False, self.env._('Too many wrong codes: the menu is locked for %s minutes.', lock.lockout_minutes)
        left = lock.max_attempts - len(lock._recent_failures(user))
        return False, self.env._('Wrong code.') + (' ' + self.env._('%s attempt(s) left.', left) if lock.max_attempts else '')

    def _send_lockout_alert(self, user):
        template = self.env.ref('access_management.mail_template_lock_alert', raise_if_not_found=False)
        if template and self.alert_emails:
            template.sudo().with_context(locked_user=user.name).send_mail(
                self.id, email_values={'email_to': self.alert_emails})
        self.message_post(body=self.env._('%s was locked out after too many wrong codes.', user.name))


class AccessLockAttempt(models.Model):
    _name = 'access.lock.attempt'
    _description = 'PIN attempt'
    _order = 'id desc'

    lock_id = fields.Many2one('access.menu.lock', required=True, ondelete='cascade', index=True)
    menu_id = fields.Many2one(related='lock_id.menu_id')
    user_id = fields.Many2one('res.users', required=True, ondelete='cascade', index=True)
    success = fields.Boolean()
    ip_address = fields.Char('IP address')
