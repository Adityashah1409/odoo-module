import ipaddress
import re
from urllib.parse import urlsplit

from odoo import api, fields, models

BOT_RE = re.compile(r'bot|crawl|spider|slurp|preview|facebookexternalhit|whatsapp|telegram|curl|wget|python-'
                    r'|headless|monitor', re.I)


class ShortUrlClick(models.Model):
    _name = 'short.url.click'
    _description = 'Short URL click'
    _order = 'date desc, id desc'

    link_id = fields.Many2one('short.url', required=True, ondelete='cascade', index=True)
    date = fields.Datetime(default=fields.Datetime.now, required=True, index=True)
    website_id = fields.Many2one('website', ondelete='set null')
    channel_id = fields.Many2one(related='link_id.channel_id', store=True)
    target_url = fields.Char(related='link_id.target_url', store=True)
    ip_network = fields.Char('Network', help='IP address with the last part removed (privacy).')
    country_id = fields.Many2one('res.country')
    referrer = fields.Char('Referrer site')
    device = fields.Selection([('desktop', 'Desktop'), ('mobile', 'Mobile'), ('tablet', 'Tablet'),
                               ('bot', 'Bot / preview')], default='desktop')
    browser = fields.Char()
    is_bot = fields.Boolean('Bot', index=True)

    @api.model
    def _anonymize_ip(self, ip):
        try:
            address = ipaddress.ip_address(ip or '')
        except ValueError:
            return False
        prefix = 24 if address.version == 4 else 48
        return str(ipaddress.ip_network(f'{address}/{prefix}', strict=False))

    @api.model
    def _parse_user_agent(self, user_agent):
        ua = user_agent or ''
        if not ua or BOT_RE.search(ua):
            return 'bot', 'Bot', True
        if re.search(r'iPad|Tablet', ua) or ('Android' in ua and 'Mobile' not in ua):
            device = 'tablet'
        elif re.search(r'Mobile|iPhone|Android', ua):
            device = 'mobile'
        else:
            device = 'desktop'
        for name, pattern in (('Edge', r'Edg/'), ('Opera', r'OPR/'), ('Samsung Internet', r'SamsungBrowser'),
                              ('Chrome', r'Chrome/'), ('Firefox', r'Firefox/'), ('Safari', r'Safari/')):
            if re.search(pattern, ua):
                return device, name, False
        return device, 'Other', False

    @api.model
    def _record(self, link, website, ip=None, user_agent=None, referrer=None, country_code=None):
        device, browser, is_bot = self._parse_user_agent(user_agent)
        referrer_host = urlsplit(referrer).netloc if referrer else False
        country = self.env['res.country'].search([('code', '=', country_code.upper())], limit=1) \
            if country_code else self.env['res.country']
        return self.sudo().create({
            'link_id': link.id, 'website_id': website.id if website else False,
            'ip_network': self._anonymize_ip(ip), 'country_id': country.id, 'referrer': referrer_host or False,
            'device': device, 'browser': browser, 'is_bot': is_bot,
        })
