import base64
import io
import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import qrcode
from PIL import Image

from odoo import api, fields, models
from odoo.exceptions import ValidationError

TOKEN_RE = re.compile(r'^[A-Za-z0-9_-]{2,64}$')


def qr_png(value, size=300):
    """PNG bytes of a QR code for ``value``, ``size`` pixels wide."""
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    code.add_data(value)
    code.make(fit=True)
    image = code.make_image(fill_color='black', back_color='white')
    image = (image.get_image() if hasattr(image, 'get_image') else image).convert('RGB')
    image = image.resize((size, size), Image.NEAREST)
    buffer = io.BytesIO()
    image.save(buffer, 'PNG', optimize=True)
    return buffer.getvalue()


class ShortUrlChannel(models.Model):
    _name = 'short.url.channel'
    _description = 'Short URL marketing channel'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    utm_source = fields.Char('UTM source', help='Value of utm_source added to the links of this channel.')
    utm_medium = fields.Char('UTM medium', default='short_link')
    active = fields.Boolean(default=True)
    link_count = fields.Integer(compute='_compute_link_count')

    def _compute_link_count(self):
        counts = dict(self.env['short.url']._read_group([('channel_id', 'in', self.ids)], ['channel_id'],
                                                        ['__count']))
        for channel in self:
            channel.link_count = counts.get(channel, 0)


class ShortUrl(models.Model):
    _name = 'short.url'
    _description = 'Short URL'
    _inherit = ['mail.thread']
    _order = 'id desc'
    _rec_name = 'token'

    name = fields.Char('Title', help='What this link is for (internal).')
    token = fields.Char('Short code', required=True, copy=False, index=True, tracking=True,
                        default=lambda self: self._default_token())
    target_url = fields.Char('Target URL', required=True, tracking=True,
                             help='A page of the website (/shop/my-product) or any http(s) address.')
    website_id = fields.Many2one('website', ondelete='cascade', index=True,
                                 help='Empty = the link works on every website.')
    short_url = fields.Char('Short URL', compute='_compute_short_url')
    qr_code = fields.Binary('QR code', compute='_compute_qr_code')
    channel_id = fields.Many2one('short.url.channel', string='Channel', index=True, tracking=True)
    campaign = fields.Char(help='Campaign name, also used as utm_campaign.')
    note = fields.Text('Notes')
    add_utm = fields.Boolean('Add UTM tags', help='Append utm_source / utm_medium / utm_campaign to the target.')
    date_expire = fields.Datetime('Expires on', tracking=True, index=True)
    active = fields.Boolean(default=True, tracking=True)
    state = fields.Selection([('valid', 'Valid'), ('expired', 'Expired'), ('archived', 'Archived')],
                             compute='_compute_state', search='_search_state')
    rule_id = fields.Many2one('short.url.rule', string='Created by rule', ondelete='set null', readonly=True)
    res_model = fields.Char('Source model', readonly=True, index=True)
    res_id = fields.Many2oneReference('Source record', model_field='res_model', readonly=True)
    click_ids = fields.One2many('short.url.click', 'link_id')
    click_count = fields.Integer('Clicks', compute='_compute_clicks', store=True)
    last_click = fields.Datetime(compute='_compute_clicks', store=True)

    _token_unique = models.Constraint('UNIQUE(token)', 'This short code is already used.')

    @api.model
    def _default_token(self):
        website = self.env['website'].browse(self.env.context.get('default_website_id')) \
            if self.env.context.get('default_website_id') else self.env['website']._short_url_current()
        return website._short_url_new_token()

    @api.constrains('token')
    def _check_token(self):
        for link in self:
            if not TOKEN_RE.match(link.token or ''):
                raise ValidationError(self.env._(
                    'Short codes use 2 to 64 letters, digits, "-" or "_" (no spaces): %s', link.token))


    @api.constrains('target_url')
    def _check_target_url(self):
        for link in self:
            url = (link.target_url or '').strip()
            if url.startswith('/') and not url.startswith('//'):
                continue
            parts = urlsplit(url)
            if parts.scheme not in ('http', 'https') or not parts.netloc:
                raise ValidationError(self.env._(
                    'The target must be a page of the website (starting with /) or an http(s) address: %s', url))

    @api.depends('token', 'website_id', 'website_id.domain')
    def _compute_short_url(self):
        current = self.env['website']._short_url_current()
        for link in self:
            website = link.website_id or current
            link.short_url = f'{website._short_url_base()}/s/{link.token}' if link.token else False

    @api.depends('short_url')
    def _compute_qr_code(self):
        for link in self:
            link.qr_code = base64.b64encode(qr_png(link.short_url)).decode() if link.short_url else False

    @api.depends('active', 'date_expire')
    def _compute_state(self):
        now = fields.Datetime.now()
        for link in self:
            if not link.active:
                link.state = 'archived'
            elif link.date_expire and link.date_expire <= now:
                link.state = 'expired'
            else:
                link.state = 'valid'

    def _search_state(self, operator, value):
        if operator not in ('=', 'in'):
            return NotImplemented
        values = {value} if operator == '=' else set(value)
        now = fields.Datetime.now()
        domains = []
        if 'valid' in values:
            domains.append(['&', ('active', '=', True), '|', ('date_expire', '=', False),
                            ('date_expire', '>', now)])
        if 'expired' in values:
            domains.append(['&', ('active', '=', True), ('date_expire', '<=', now)])
        if 'archived' in values:
            domains.append([('active', '=', False)])
        if not domains:
            return [('id', '=', False)]
        result = domains[0]
        for domain in domains[1:]:
            result = ['|'] + result + domain
        return result

    @api.depends('click_ids', 'click_ids.is_bot')
    def _compute_clicks(self):
        data = {link: (count, last) for link, count, last in self.env['short.url.click']._read_group(
            [('link_id', 'in', self.ids), ('is_bot', '=', False)], ['link_id'], ['__count', 'date:max'])}
        for link in self:
            link.click_count, link.last_click = data.get(link, (0, False))

    def _assert_free_token(self, token):
        """Clear message instead of the database error when a code is taken."""
        if self.sudo().with_context(active_test=False).search_count([('token', '=', token),
                                                                     ('id', 'not in', self.ids)]):
            raise ValidationError(self.env._('The short code "%s" is already used.', token))

    @api.model_create_multi
    def create(self, vals_list):
        seen = set()
        for vals in vals_list:
            if vals.get('target_url'):
                vals['target_url'] = vals['target_url'].strip()
            if vals.get('token'):
                vals['token'] = vals['token'].strip()
                if vals['token'] in seen:
                    raise ValidationError(self.env._('The short code "%s" is already used.', vals['token']))
                seen.add(vals['token'])
                self.browse()._assert_free_token(vals['token'])
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('target_url'):
            vals['target_url'] = vals['target_url'].strip()
        if vals.get('token'):
            vals['token'] = vals['token'].strip()
            self._assert_free_token(vals['token'])
        return super().write(vals)

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def action_regenerate_token(self):
        for link in self:
            link.token = (link.website_id or self.env['website']._short_url_current())._short_url_new_token()

    def action_view_clicks(self):
        action = self.env['ir.actions.act_window']._for_xml_id('short_urls.action_short_url_click')
        action['domain'] = [('link_id', 'in', self.ids)]
        action['context'] = {'search_default_humans': 1}
        return action

    def action_open_target(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.target_url, 'target': 'new'}

    def action_download_qr(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': f'/short_urls/qr/{quote(self.token)}.png?download=1',
                'target': 'download'}

    # ------------------------------------------------------------------
    # redirection
    # ------------------------------------------------------------------
    @api.model
    def _find_for_redirect(self, token, website):
        """The link to follow for ``token`` on ``website`` (website links first, then global ones)."""
        links = self.sudo().with_context(active_test=False).search(
            [('token', '=', token), ('website_id', 'in', [website.id, False])])
        return links.sorted(lambda l: not l.website_id)[:1]

    def _redirect_url(self):
        self.ensure_one()
        url = self.target_url
        if not self.add_utm:
            return url
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        channel = self.channel_id
        tags = {
            'utm_source': channel.utm_source or (channel.name or 'short_link').lower().replace(' ', '_'),
            'utm_medium': channel.utm_medium or 'short_link',
            'utm_campaign': self.campaign or self.token,
        }
        for key, value in tags.items():
            query.setdefault(key, value)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    # ------------------------------------------------------------------
    # page dialog (website editor) and snippets
    # ------------------------------------------------------------------
    @api.model
    def _page_domain(self, website, path):
        path = (path or '/').split('?')[0].split('#')[0] or '/'
        base = website._short_url_base()
        targets = {path, base + path}
        if path != '/' and path.endswith('/'):
            targets |= {path.rstrip('/'), base + path.rstrip('/')}
        return [('target_url', 'in', list(targets)), ('website_id', 'in', [website.id, False])]

    def _page_dict(self):
        self.ensure_one()
        return {
            'id': self.id, 'token': self.token, 'name': self.name or '', 'short_url': self.short_url,
            'target_url': self.target_url, 'clicks': self.click_count, 'state': self.state,
            'channel': self.channel_id.name or '', 'channel_id': self.channel_id.id,
            'date_expire': fields.Datetime.to_string(self.date_expire) if self.date_expire else False,
            'qr_url': f'/short_urls/qr/{quote(self.token)}.png',
            'website': self.website_id.name or '',
        }

    @api.model
    def page_links(self, website_id, path):
        website = self.env['website'].browse(website_id)
        links = self.with_context(active_test=False).search(self._page_domain(website, path))
        channels = self.env['short.url.channel'].search([])
        return {
            'links': [link._page_dict() for link in links],
            'channels': [{'id': c.id, 'name': c.name} for c in channels],
            'path': path,
        }

    @api.model
    def create_for_page(self, website_id, path, token=False, channel_id=False, date_expire=False, name=False):
        website = self.env['website'].browse(website_id)
        days = website.short_url_validity_days
        if not date_expire and days:
            date_expire = fields.Datetime.add(fields.Datetime.now(), days=days)
        link = self.create({
            'target_url': path.split('#')[0] or '/', 'website_id': website.id, 'channel_id': channel_id or False,
            'token': (token or '').strip() or website._short_url_new_token(), 'date_expire': date_expire,
            'name': name or False,
        })
        return link._page_dict()

    @api.model
    def _snippet_link(self, website, path, create=False):
        link = self.sudo().search(self._page_domain(website, path) + [('state', '=', 'valid')],
                                  order='channel_id desc, id', limit=1)
        if not link and create:
            link = self.sudo().create({'target_url': path, 'website_id': website.id,
                                       'token': website._short_url_new_token(),
                                       'name': self.env._('Page link (snippet)')})
        return link
