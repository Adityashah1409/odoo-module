import secrets

from odoo import api, fields, models

ALPHABET = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no 0/O, 1/l/I


class Website(models.Model):
    _inherit = 'website'

    short_url_token_style = fields.Selection([('random', 'Random letters and digits'),
                                              ('sequence', 'Sequential number')],
                                             string='Short code style', default='random', required=True)
    short_url_token_length = fields.Integer('Short code length', default=6)
    short_url_validity_days = fields.Integer('Default validity (days)', default=0,
                                             help='Validity of automatically created links. 0 = no expiry.')

    @api.model
    def _short_url_current(self):
        """Website of the current request (or the default one)."""
        return self.env.website or self.env.ref('base.default_website', raise_if_not_found=False) \
            or self.env['website'].search([], limit=1)

    def _short_url_new_token(self):
        """A free short code following the website settings."""
        website = self[:1]
        ShortUrl = self.env['short.url'].sudo().with_context(active_test=False)
        if (website.short_url_token_style or 'random') == 'sequence':
            for _attempt in range(50):
                token = self.env['ir.sequence'].sudo().next_by_code('short.url')
                if not ShortUrl.search_count([('token', '=', token)]):
                    return token
        length = min(max(website.short_url_token_length or 6, 3), 32)
        for attempt in range(100):
            token = ''.join(secrets.choice(ALPHABET) for _i in range(length + attempt // 20))
            if not ShortUrl.search_count([('token', '=', token)]):
                return token
        raise ValueError('No free short code found')

    def _short_url_base(self):
        self.ensure_one()
        base = (self.domain or self.get_base_url() or '').rstrip('/')
        if base and not base.startswith('http'):
            base = 'https://' + base
        return base
