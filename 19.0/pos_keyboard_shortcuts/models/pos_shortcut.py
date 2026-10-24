from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

SCREENS = [
    ('all', 'All screens'),
    ('product', 'Product screen'),
    ('payment', 'Payment screen'),
    ('receipt', 'Receipt screen'),
    ('orders', 'Orders list'),
]
ACTIONS = [
    # product screen
    ('pay', 'Go to payment'),
    ('qty_mode', 'Numpad: quantity'),
    ('discount_mode', 'Numpad: discount'),
    ('price_mode', 'Numpad: price'),
    ('search_product', 'Search products'),
    ('delete_line', 'Delete selected line'),
    ('line_up', 'Select previous line'),
    ('line_down', 'Select next line'),
    # payment screen
    ('payment_method', 'Add payment with a method'),
    ('remove_payment', 'Remove selected payment'),
    ('validate', 'Validate the order'),
    # receipt screen
    ('next_order', 'Next order'),
    # anywhere
    ('new_order', 'New order'),
    ('customer', 'Choose customer'),
    ('orders', 'Open orders list'),
    ('back', 'Back to products'),
    ('help', 'Show shortcuts'),
]
MODIFIERS = ('ctrl', 'alt', 'shift')
NAMED_KEYS = {
    'enter', 'escape', 'delete', 'backspace', 'insert', 'tab', 'space', 'home', 'end', 'pageup', 'pagedown',
    'arrowup', 'arrowdown', 'arrowleft', 'arrowright', '+', '-', '*', '/', '.', ',', '?',
} | {f'f{i}' for i in range(1, 13)}
ALIASES = {'control': 'ctrl', 'esc': 'escape', 'del': 'delete', 'ins': 'insert', 'up': 'arrowup', 'down': 'arrowdown',
           'left': 'arrowleft', 'right': 'arrowright', 'return': 'enter', 'plus': '+'}

DEFAULTS = [
    ('product', 'pay', 'shift+p'), ('product', 'qty_mode', 'q'), ('product', 'discount_mode', 'd'),
    ('product', 'price_mode', 'r'), ('product', 'search_product', 'f'), ('product', 'delete_line', 'delete'),
    ('product', 'line_up', 'arrowup'), ('product', 'line_down', 'arrowdown'),
    ('payment', 'validate', 'v'), ('payment', 'remove_payment', 'shift+delete'),
    ('receipt', 'next_order', 'n'),
    ('all', 'new_order', 'insert'), ('all', 'customer', 'shift+c'), ('all', 'orders', 'shift+g'),
    ('all', 'back', 'escape'), ('all', 'help', 'f1'),
]


def normalize_key(value):
    """'Shift + P' -> 'shift+p', 'Ctrl+Del' -> 'ctrl+delete', 'shift++' -> 'shift++'. Raises ValueError."""
    raw = (value or '').strip().lower().replace(' ', '')
    if not raw:
        raise ValueError("a key is required")
    if raw == '+':
        parts = ['+']
    elif raw.endswith('++'):
        parts = raw[:-2].split('+') + ['+']
    else:
        parts = raw.split('+')
    parts = [ALIASES.get(p, p) for p in parts]
    *modifiers, key = parts
    if any(m not in MODIFIERS for m in modifiers) or len(set(modifiers)) != len(modifiers):
        raise ValueError("use ctrl, alt and shift as modifiers, e.g. shift+p")
    if len(key) != 1 and key not in NAMED_KEYS:
        raise ValueError(f"unknown key {key}")
    return '+'.join([m for m in MODIFIERS if m in modifiers] + [key])


class PosShortcut(models.Model):
    _name = 'pos.shortcut'
    _description = 'POS Keyboard Shortcut'
    _order = 'config_id, screen, sequence, id'

    config_id = fields.Many2one('pos.config', string="Point of Sale", required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    screen = fields.Selection(SCREENS, required=True, default='all')
    action = fields.Selection(ACTIONS, required=True)
    key = fields.Char(required=True, help="e.g. shift+p, f1, delete, ctrl+alt+n")
    payment_method_id = fields.Many2one('pos.payment.method',
                                        domain="[('id', 'in', allowed_payment_method_ids)]")
    allowed_payment_method_ids = fields.Many2many(related='config_id.payment_method_ids')

    _key_uniq = models.Constraint('UNIQUE(config_id, screen, key)',
                                  "This key is already used on this screen of the point of sale.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('key'):
                vals['key'] = self._normalize(vals['key'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('key'):
            vals['key'] = self._normalize(vals['key'])
        return super().write(vals)

    @api.model
    def _normalize(self, key):
        try:
            return normalize_key(key)
        except ValueError as e:
            raise ValidationError(_("Invalid shortcut %(key)s: %(error)s", key=key, error=e)) from e

    @api.constrains('action', 'payment_method_id', 'screen')
    def _check_action(self):
        for shortcut in self:
            if shortcut.action == 'payment_method' and not shortcut.payment_method_id:
                raise ValidationError(_("Choose the payment method of shortcut %s.", shortcut.key))
            if shortcut.action == 'payment_method' and shortcut.screen not in ('payment', 'all'):
                raise ValidationError(_("Payment method shortcuts work on the payment screen."))

    def _pos_data(self):
        labels = dict(ACTIONS)
        return [{
            'id': s.id, 'screen': s.screen, 'action': s.action, 'key': s.key,
            'payment_method_id': s.payment_method_id.id or False,
            'label': s.payment_method_id.name if s.action == 'payment_method' else labels[s.action],
        } for s in self.filtered('active')]
