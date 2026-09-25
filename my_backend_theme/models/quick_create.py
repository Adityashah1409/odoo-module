import ast
import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ICON_PATTERN = re.compile(r'^[a-z0-9_]+$')

# (model, label, icon, context) offered by "Add suggested entries" when the
# corresponding app is installed.
SUGGESTED_ENTRIES = [
    ('res.partner', "Contact", 'person_add', {}),
    ('crm.lead', "Lead", 'handshake', {}),
    ('sale.order', "Quotation", 'sell', {}),
    ('account.move', "Customer Invoice", 'receipt_long', {'default_move_type': 'out_invoice'}),
    ('purchase.order', "Purchase Order", 'shopping_cart', {}),
    ('project.task', "Task", 'task', {}),
    ('product.template', "Product", 'inventory_2', {}),
    ('hr.employee', "Employee", 'badge', {}),
]


def parse_context(value):
    """Parse a context written as a Python dict literal; never evaluates code."""
    if not value:
        return {}
    parsed = ast.literal_eval(value)
    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise ValueError(value)
    return parsed


class MyThemeQuickCreate(models.Model):
    """A model users can create records of from the "Quick Create" menu."""

    _name = 'my.theme.quick.create'
    _description = 'Backend Theme Quick Create Entry'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    model_id = fields.Many2one(
        'ir.model', string="Model", required=True, ondelete='cascade',
        domain=[('transient', '=', False)],
    )
    model = fields.Char(related='model_id.model', store=True, string="Model Name")
    icon = fields.Char(
        default='add',
        help="Name of an Odoo UI icon, for example: person, shopping_cart, description.",
    )
    context = fields.Char(
        default='{}',
        help="Default values for the new record, as a dictionary, e.g. {'default_move_type': 'out_invoice'}.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    group_ids = fields.Many2many(
        'res.groups', string="Restricted to Groups",
        help="Only members of these groups see the entry. Leave empty for everyone who can create such records.",
    )

    @api.constrains('icon')
    def _check_icon(self):
        for entry in self:
            if entry.icon and not ICON_PATTERN.match(entry.icon):
                raise ValidationError(_("The icon name may only contain lowercase letters, digits and underscores."))

    @api.constrains('context')
    def _check_context(self):
        for entry in self:
            try:
                parse_context(entry.context)
            except (ValueError, SyntaxError, MemoryError, RecursionError):
                raise ValidationError(_("The context must be a dictionary such as {'default_name': 'New'}."))

    @api.model
    def _add_suggested_entries(self):
        """Create entries for the suggested models of installed apps."""
        existing = set(self.with_context(active_test=False).search([]).mapped('model'))
        sequence = 10
        for model, name, icon, context in SUGGESTED_ENTRIES:
            sequence += 10
            if model in existing or model not in self.env:
                continue
            self.create({
                'name': name,
                'model_id': self.env['ir.model']._get_id(model),
                'icon': icon,
                'context': repr(context),
                'sequence': sequence,
            })

    @api.model
    def get_quick_create_items(self):
        """Entries the current user may use: visible to their groups and on a
        model they are allowed to create records of."""
        if not self.has_access('read'):
            return []
        items = []
        user_groups = self.env.user.all_group_ids
        for entry in self.search([]):
            if entry.group_ids and not (entry.group_ids & user_groups):
                continue
            model = entry.model
            if model not in self.env or not self.env[model].has_access('create'):
                continue
            items.append({
                'id': entry.id,
                'name': entry.name,
                'model': model,
                'icon': entry.icon or 'add',
                'context': parse_context(entry.context),
            })
        return items
