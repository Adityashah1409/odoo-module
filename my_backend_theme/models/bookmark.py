from urllib.parse import urlsplit

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def is_safe_backend_url(url):
    """Only relative web client URLs (``/odoo...``) are stored: no scheme and
    no host, which rules out open redirects and ``javascript:`` links."""
    if not isinstance(url, str) or len(url) > 2000:
        return False
    parts = urlsplit(url)
    if parts.scheme or parts.netloc:
        return False
    return parts.path == '/odoo' or parts.path.startswith('/odoo/')


class MyThemeBookmark(models.Model):
    _name = 'my.theme.bookmark'
    _inherit = ['my.theme.record.link.mixin']
    _description = 'Backend Theme Bookmark'
    _order = 'sequence, id desc'

    name = fields.Char(required=True)
    user_id = fields.Many2one(
        'res.users', required=True, index=True, ondelete='cascade',
        default=lambda self: self.env.user,
    )
    url = fields.Char(string="URL", required=True)
    res_model = fields.Char(string="Model")
    res_id = fields.Many2oneReference(model_field='res_model', string="Record")
    company_id = fields.Many2one(
        'res.company', string="Company", ondelete='cascade',
        help="When set, the bookmark is only listed while working in this company.",
    )
    sequence = fields.Integer(default=10)

    _unique_user_url = models.Constraint(
        'UNIQUE(user_id, url)',
        "This page is already bookmarked.",
    )

    @api.constrains('url')
    def _check_url(self):
        for bookmark in self:
            if not is_safe_backend_url(bookmark.url):
                raise ValidationError(_("A bookmark must point to a page of the Odoo backend."))

    @api.constrains('res_model')
    def _check_res_model(self):
        for bookmark in self:
            if bookmark.res_model and not self._is_valid_business_model(bookmark.res_model):
                raise ValidationError(_("Unknown model: %s", bookmark.res_model))

    @api.model
    def _current_user_domain(self):
        company_ids = self.env.context.get('allowed_company_ids') or self.env.companies.ids
        return [
            ('user_id', '=', self.env.uid),
            '|', ('company_id', '=', False), ('company_id', 'in', company_ids),
        ]

    @api.model
    def get_bookmarks(self):
        bookmarks = self.search(self._current_user_domain())._filter_accessible()
        return [bookmark._format() for bookmark in bookmarks]

    @api.model
    def toggle_bookmark(self, url, name, res_model=False, res_id=False):
        """Bookmark ``url`` for the current user, or remove the bookmark if it
        already exists. Returns the bookmark, or False once removed."""
        existing = self.search([('user_id', '=', self.env.uid), ('url', '=', url)], limit=1)
        if existing:
            existing.unlink()
            return False
        if res_model and not self._is_valid_business_model(res_model):
            res_model = res_id = False
        if res_model and res_id:
            # Only bookmark records the user can actually read.
            self.env[res_model].browse(int(res_id)).check_access('read')
        bookmark = self.create({
            'name': (name or url)[:200],
            'url': url,
            'res_model': res_model or False,
            'res_id': int(res_id) if res_model and res_id else False,
        })
        return bookmark._format()

    def rename(self, name):
        self.ensure_one()
        if name and name.strip():
            self.name = name.strip()[:200]
        return self._format()

    def _format(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'res_model': self.res_model or False,
            'res_id': self.res_id or False,
            'company_id': self.company_id.id or False,
        }
