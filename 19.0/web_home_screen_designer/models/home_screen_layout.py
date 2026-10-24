import json

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

GRADIENTS = [
    ('aurora', 'Aurora'), ('sunset', 'Sunset'), ('ocean', 'Ocean'), ('forest', 'Forest'),
    ('dusk', 'Dusk'), ('peach', 'Peach'), ('slate', 'Slate'), ('mint', 'Mint'),
]
SELECTIONS = {
    'background_type': ['default', 'gradient', 'image'],
    'gradient': [key for key, _label in GRADIENTS],
    'overlay': ['none', 'light', 'dark'],
    'tile_style': ['plain', 'glass'],
    'hover_effect': ['none', 'lift', 'grow', 'bounce'],
}
# field -> (min, max); columns 0 means "fit to the screen"
RANGES = {
    'columns': (0, 12), 'gap': (0, 48), 'icon_size': (32, 128), 'icon_radius': (0, 50),
    'font_size': (10, 20), 'overlay_opacity': (0, 90), 'blur': (0, 20),
}
BOOLEANS = ['show_names', 'show_clock', 'show_seconds', 'show_greeting', 'show_search']
LISTS = ['app_order', 'hidden_apps']


class HomeScreenLayout(models.Model):
    _name = 'home.screen.layout'
    _description = 'Home Screen Layout'

    user_id = fields.Many2one('res.users', ondelete='cascade', index=True,
                              help='Empty for the company layout.')
    company_id = fields.Many2one('res.company', required=True, ondelete='cascade',
                                 default=lambda self: self.env.company)
    background_type = fields.Selection([
        ('default', 'Default'), ('gradient', 'Gradient'), ('image', 'Picture'),
    ], default='gradient', required=True)
    gradient = fields.Selection(GRADIENTS, default='aurora', required=True)
    background_image = fields.Image(max_width=2560, max_height=1600)
    overlay = fields.Selection([('none', 'None'), ('light', 'Light'), ('dark', 'Dark')], default='none', required=True)
    overlay_opacity = fields.Integer(default=30)
    blur = fields.Integer(default=0)
    columns = fields.Integer(default=0, help='0 = as many as fit')
    gap = fields.Integer(default=24)
    icon_size = fields.Integer(default=64)
    icon_radius = fields.Integer(default=22, help='Corner radius in % of the icon size (50 = round)')
    font_size = fields.Integer(default=13)
    show_names = fields.Boolean(default=True)
    tile_style = fields.Selection([('plain', 'Plain'), ('glass', 'Glass')], default='plain', required=True)
    hover_effect = fields.Selection([
        ('none', 'None'), ('lift', 'Lift'), ('grow', 'Grow'), ('bounce', 'Bounce'),
    ], default='lift', required=True)
    show_clock = fields.Boolean(default=True)
    show_seconds = fields.Boolean(default=False)
    show_greeting = fields.Boolean(default=True)
    show_search = fields.Boolean(default=True)
    app_order = fields.Char(default='[]', help='JSON list of app menu XML IDs')
    hidden_apps = fields.Char(default='[]', help='JSON list of app menu XML IDs hidden from the home screen')

    _user_uniq = models.UniqueIndex('(user_id) WHERE user_id IS NOT NULL', 'A user has one home screen layout.')
    _company_uniq = models.UniqueIndex('(company_id) WHERE user_id IS NULL', 'A company has one home screen layout.')

    # ------------------------------------------------------------------ helpers
    @api.model
    def _defaults(self):
        values = {name: self._fields[name].default(self) for name in self._layout_fields()
                  if self._fields[name].default}
        values.update({name: [] for name in LISTS})
        return values

    @api.model
    def _layout_fields(self):
        return list(SELECTIONS) + list(RANGES) + BOOLEANS + LISTS

    def _to_dict(self):
        self.ensure_one()
        values = {name: self[name] for name in self._layout_fields() if name not in LISTS}
        for name in LISTS:
            try:
                values[name] = [x for x in json.loads(self[name] or '[]') if isinstance(x, str)]
            except ValueError:
                values[name] = []
        values['background_url'] = (
            f'/web/image/home.screen.layout/{self.id}/background_image?unique={int(self.write_date.timestamp())}'
            if self.background_image else False)
        return values

    @api.model
    def _clean_values(self, values):
        """Keep known keys only, clamp numbers, check selections, serialize lists."""
        clean = {}
        for name, allowed in SELECTIONS.items():
            if name in values:
                if values[name] not in allowed:
                    raise UserError(self.env._('Invalid value for %(field)s: %(value)s', field=name, value=values[name]))
                clean[name] = values[name]
        for name, (low, high) in RANGES.items():
            if name in values:
                try:
                    number = int(values[name])
                except (TypeError, ValueError):
                    raise UserError(self.env._('%s must be a number.', name)) from None
                clean[name] = min(max(number, low), high)
        if clean.get('columns') and clean['columns'] < 3:
            clean['columns'] = 3
        for name in BOOLEANS:
            if name in values:
                clean[name] = bool(values[name])
        for name in LISTS:
            if name in values:
                items = values[name] or []
                if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
                    raise UserError(self.env._('%s must be a list of app XML IDs.', name))
                clean[name] = json.dumps(items[:200])
        if 'background_image' in values:
            clean['background_image'] = values['background_image'] or False
        return clean

    @api.model
    def _company_layout(self, company=None):
        company = company or self.env.company
        return self.sudo().search([('user_id', '=', False), ('company_id', '=', company.id)], limit=1)

    @api.model
    def _user_layout(self):
        return self.sudo().search([('user_id', '=', self.env.uid)], limit=1)

    # ---------------------------------------------------------------------- API
    @api.model
    def get_home_screen(self):
        company = self.env.company
        allow = company.home_screen_allow_user_layout
        layout = (self._user_layout() if allow else self.browse()) or self._company_layout()
        scope = 'user' if layout.user_id else ('company' if layout else 'default')
        user = self.env.user
        action = self.env.ref('web_home_screen_designer.action_home_screen')
        return {
            'layout': layout._to_dict() if layout else self._defaults(),
            'scope': scope,
            'is_admin': user.has_group('base.group_system'),
            'allow_user_layout': allow,
            'has_company_layout': bool(self._company_layout()),
            'open_on_login': user.action_id.id == action.id,
            'first_name': (user.name or '').split(' ')[0],
            'gradients': [{'key': key, 'label': label} for key, label in GRADIENTS],
        }

    @api.model
    def save_home_screen(self, values, scope='user', open_on_login=None, allow_user_layout=None):
        is_admin = self.env.user.has_group('base.group_system')
        company = self.env.company
        if scope == 'company':
            if not is_admin:
                raise AccessError(self.env._('Only administrators can change the company home screen.'))
            if allow_user_layout is not None:
                company.sudo().home_screen_allow_user_layout = bool(allow_user_layout)
            layout = self._company_layout()
            target = {'user_id': False, 'company_id': company.id}
        elif scope == 'user':
            if not company.home_screen_allow_user_layout and not is_admin:
                raise UserError(self.env._('Your company does not allow personal home screens.'))
            layout = self._user_layout()
            target = {'user_id': self.env.uid, 'company_id': company.id}
        else:
            raise UserError(self.env._('Unknown scope %s.', scope))
        clean = self._clean_values(values or {})
        if layout:
            layout.write(clean)
        else:
            layout = self.sudo().create(dict(clean, **target))
        if open_on_login is not None:
            self._set_open_on_login(open_on_login)
        return self.get_home_screen()

    @api.model
    def reset_home_screen(self):
        """Forget the personal layout: the user sees the company layout again."""
        self._user_layout().unlink()
        return self.get_home_screen()

    @api.model
    def _set_open_on_login(self, enabled):
        action = self.env.ref('web_home_screen_designer.action_home_screen')
        user = self.env.user.sudo()
        if enabled:
            user.action_id = action.id
        elif user.action_id.id == action.id:
            user.action_id = False
