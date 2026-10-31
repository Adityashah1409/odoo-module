from odoo import http
from odoo.http import request

from ..models.short_url import qr_png


class ShortUrlController(http.Controller):

    @http.route('/s/<string:token>', type='http', auth='public', website=True, sitemap=False, methods=['GET'])
    def short_url_redirect(self, token, **kw):
        website = request.env['website']._short_url_current()
        link = request.env['short.url']._find_for_redirect(token, website)
        if not link or link.state != 'valid':
            return request.render('short_urls.link_unavailable', {'link': link, 'token': token}, status=404)
        httprequest = request.httprequest
        country_code = False
        try:
            country_code = request.geoip.country_code
        except Exception:  # noqa: BLE001 - GeoIP database missing
            country_code = False
        request.env['short.url.click']._record(
            link, website, ip=httprequest.remote_addr, user_agent=httprequest.user_agent.string,
            referrer=httprequest.referrer, country_code=country_code)
        return request.redirect(link._redirect_url(), code=302, local=False)

    @http.route('/short_urls/qr/<string:token>.png', type='http', auth='public', website=True, sitemap=False,
                methods=['GET'])
    def short_url_qr(self, token, download=False, size=300, **kw):
        website = request.env['website']._short_url_current()
        link = request.env['short.url']._find_for_redirect(token, website)
        if not link or not link.active:
            raise request.not_found()
        size = min(max(int(size or 300), 100), 1000)
        image = qr_png(link.short_url, size)
        headers = [('Content-Type', 'image/png'), ('Cache-Control', 'public, max-age=3600')]
        if download:
            headers.append(('Content-Disposition', f'attachment; filename="qr-{link.token}.png"'))
        return request.make_response(image, headers)

    @http.route('/short_urls/page_link', type='jsonrpc', auth='public', website=True, methods=['POST'])
    def short_url_page_link(self, path='/', **kw):
        """Short link of a page, for the "Short URL" snippets."""
        website = request.env['website']._short_url_current()
        designer = request.env.user.has_group('website.group_website_designer')
        link = request.env['short.url']._snippet_link(website, path, create=designer)
        if not link:
            return False
        return {'token': link.token, 'short_url': link.short_url, 'qr_url': f'/short_urls/qr/{link.token}.png'}
