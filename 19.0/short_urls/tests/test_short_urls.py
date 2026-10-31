from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, new_test_user, tagged

CHROME = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
          'Chrome/141.0 Safari/537.36')
IPHONE = ('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) '
          'Version/18.0 Mobile/15E148 Safari/604.1')


@tagged('post_install', '-at_install')
class TestShortUrls(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website']._short_url_current()
        cls.ShortUrl = cls.env['short.url']
        cls.link = cls.ShortUrl.create({'token': 'spring', 'target_url': '/contactus',
                                        'website_id': cls.website.id})

    def visit(self, token, ua=CHROME, referrer=None):
        headers = {'User-Agent': ua}
        if referrer:
            headers['Referer'] = referrer
        return self.url_open(f'/s/{token}', allow_redirects=False, headers=headers)

    def test_generated_tokens(self):
        self.website.write({'short_url_token_style': 'random', 'short_url_token_length': 8})
        tokens = {self.ShortUrl.create({'target_url': '/shop'}).token for _i in range(20)}
        self.assertEqual(len(tokens), 20)
        self.assertTrue(all(len(t) == 8 and not set(t) & set('0O1lI') for t in tokens))
        self.website.short_url_token_style = 'sequence'
        first = self.ShortUrl.create({'target_url': '/shop'}).token
        second = self.ShortUrl.create({'target_url': '/shop'}).token
        self.assertTrue(first.isdigit())
        self.assertEqual(int(second), int(first) + 1)

    def test_validation(self):
        for token in ('has space', 'a', 'é-accent', 'x' * 65):
            with self.subTest(token=token), self.assertRaises(ValidationError):
                self.ShortUrl.create({'token': token, 'target_url': '/'})
        for url in ('javascript:alert(1)', 'ftp://files.example.com', '//evil.example.com', 'shop'):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                self.ShortUrl.create({'target_url': url})
        with self.assertRaises(ValidationError):
            self.ShortUrl.create({'token': 'spring', 'target_url': '/'})
        link = self.ShortUrl.create({'token': '  promo-2027 ', 'target_url': ' https://example.com/x '})
        self.assertEqual((link.token, link.target_url), ('promo-2027', 'https://example.com/x'))

    def test_redirect_and_clicks(self):
        response = self.visit('spring', referrer='https://www.facebook.com/somepost')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/contactus'))
        self.visit('spring', ua=IPHONE)
        self.visit('spring', ua='facebookexternalhit/1.1')
        self.link.invalidate_recordset()
        self.assertEqual(self.link.click_count, 2, 'link previews are not counted')
        clicks = self.link.click_ids.sorted('id')
        self.assertEqual(clicks.mapped('device'), ['desktop', 'mobile', 'bot'])
        self.assertEqual(clicks[0].browser, 'Chrome')
        self.assertEqual(clicks[1].browser, 'Safari')
        self.assertEqual(clicks[0].referrer, 'www.facebook.com')
        self.assertEqual(clicks[0].ip_network, '127.0.0.0/24')
        self.assertTrue(self.link.last_click)

    def test_utm_tags(self):
        channel = self.env.ref('short_urls.channel_facebook')
        link = self.ShortUrl.create({'token': 'fbspring', 'target_url': '/shop?category=3', 'channel_id': channel.id,
                                     'campaign': 'spring-2027', 'add_utm': True})
        location = self.visit('fbspring').headers['Location']
        query = parse_qs(urlsplit(location).query)
        self.assertEqual(query, {'category': ['3'], 'utm_source': ['facebook'], 'utm_medium': ['social'],
                                 'utm_campaign': ['spring-2027']})
        self.assertEqual(link.click_ids.channel_id, channel)

    def test_expired_archived_unknown_and_global(self):
        self.link.date_expire = fields.Datetime.now() - timedelta(days=1)
        self.assertEqual(self.link.state, 'expired')
        response = self.visit('spring')
        self.assertEqual(response.status_code, 404)
        self.assertIn('expired', response.text)
        self.assertEqual(self.visit('nothing-here').status_code, 404)
        self.link.write({'date_expire': False, 'active': False})
        self.assertEqual(self.visit('spring').status_code, 404)
        self.assertEqual(self.ShortUrl.with_context(active_test=False).search_count(
            [('state', '=', 'archived'), ('id', '=', self.link.id)]), 1)
        # a link without website works on every website
        other = self.env['website'].create({'name': 'Other site'})
        self.ShortUrl.create({'token': 'global', 'target_url': 'https://example.com/global'})
        local = self.ShortUrl.create({'token': 'otheronly', 'target_url': '/', 'website_id': other.id})
        self.assertEqual(self.visit('global').headers['Location'], 'https://example.com/global')
        self.assertEqual(self.visit('otheronly').status_code, 404, 'link of another website')
        self.assertEqual(self.ShortUrl._find_for_redirect('otheronly', other), local)
        valid = self.ShortUrl.search([('state', '=', 'valid')])
        self.assertNotIn(self.link, valid)
        self.assertIn(local, valid)

    def test_qr_code(self):
        self.assertTrue(self.link.qr_code)
        response = self.url_open('/short_urls/qr/spring.png?download=1&size=200')
        self.assertEqual(response.headers['Content-Type'], 'image/png')
        self.assertIn('qr-spring.png', response.headers['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'\x89PNG'))
        self.assertEqual(self.url_open('/short_urls/qr/unknown.png').status_code, 404)
        action = self.link.action_download_qr()
        self.assertIn('/short_urls/qr/spring.png', action['url'])

    def test_rules(self):
        page = self.env['website.page'].create({
            'name': 'Spring offers', 'url': '/spring-offers', 'type': 'qweb', 'website_id': self.website.id,
            'is_published': True, 'arch': '<t t-call="website.layout"><div id="wrap"/></t>', 'key': 'test.spring'})
        draft = self.env['website.page'].create({
            'name': 'Draft', 'url': '/draft-page', 'type': 'qweb', 'website_id': self.website.id,
            'is_published': False, 'arch': '<t t-call="website.layout"><div id="wrap"/></t>', 'key': 'test.draft'})
        self.website.short_url_validity_days = 30
        rule = self.env['short.url.rule'].create({
            'name': 'Pages', 'domain': "[('url', 'like', '-')]", 'website_id': self.website.id,
            'channel_id': self.env.ref('short_urls.channel_print').id})
        rule.action_apply()
        links = rule.link_ids
        self.assertIn('/spring-offers', links.mapped('target_url'))
        self.assertNotIn('/draft-page', links.mapped('target_url'))
        spring = links.filtered(lambda l: l.target_url == '/spring-offers')
        self.assertEqual((spring.res_model, spring.res_id), ('website.page', page.id))
        self.assertEqual(spring.channel_id.name, 'Print / flyer (QR)')
        self.assertAlmostEqual(spring.date_expire, fields.Datetime.now() + timedelta(days=30),
                               delta=timedelta(minutes=5))
        count = len(links)
        rule.action_apply()
        self.assertEqual(len(rule.link_ids), count, 'applying twice creates nothing')
        draft.is_published = True
        self.env['short.url.rule']._cron_apply()
        self.assertIn('/draft-page', rule.link_ids.mapped('target_url'))
        with self.assertRaises(Exception):
            self.env['short.url.rule'].create({'name': 'Bad', 'domain': "[('nope', '=', 1)]"})

    def test_page_dialog_methods(self):
        data = self.ShortUrl.page_links(self.website.id, '/contactus')
        self.assertEqual([l['token'] for l in data['links']], ['spring'])
        self.assertTrue(data['channels'])
        self.website.short_url_validity_days = 7
        created = self.ShortUrl.create_for_page(self.website.id, '/contactus', token='contact-flyer',
                                                channel_id=self.env.ref('short_urls.channel_print').id)
        self.assertEqual(created['token'], 'contact-flyer')
        self.assertTrue(created['date_expire'])
        # absolute target of the same page is found too
        base = self.website._short_url_base()
        self.ShortUrl.create({'token': 'abs', 'target_url': base + '/contactus'})
        tokens = {l['token'] for l in self.ShortUrl.page_links(self.website.id, '/contactus')['links']}
        self.assertEqual(tokens, {'spring', 'contact-flyer', 'abs'})

    def test_snippet_route_and_access(self):
        self.authenticate(None, None)
        result = self.make_jsonrpc_request('/short_urls/page_link', {'path': '/contactus'})
        self.assertEqual(result['token'], 'spring')
        self.assertIsNone(self.make_jsonrpc_request('/short_urls/page_link', {'path': '/aboutus'}) or None)
        self.assertFalse(self.ShortUrl.search_count([('target_url', '=', '/aboutus')]),
                         'visitors do not create links')
        self.authenticate('admin', 'admin')
        result = self.make_jsonrpc_request('/short_urls/page_link', {'path': '/aboutus'})
        self.assertTrue(result['short_url'].endswith('/s/' + result['token']))
        # rights
        editor = new_test_user(self.env, 'editor', groups='base.group_user,website.group_website_restricted_editor')
        portal = new_test_user(self.env, 'portaluser', groups='base.group_portal')
        link = self.ShortUrl.with_user(editor).create({'target_url': '/shop', 'token': 'editor-link'})
        self.assertEqual(link.create_uid, editor)
        with self.assertRaises(AccessError):
            link.with_user(editor).unlink()
        with self.assertRaises(AccessError):
            self.ShortUrl.with_user(portal).search([])
        with self.assertRaises(AccessError):
            self.env['short.url.rule'].with_user(editor).create({'name': 'x'})

    def test_regenerate_and_views(self):
        old = self.link.token
        self.link.action_regenerate_token()
        self.assertNotEqual(self.link.token, old)
        self.assertEqual(self.visit(old).status_code, 404)
        self.assertEqual(self.visit(self.link.token).status_code, 302)
        action = self.link.action_view_clicks()
        self.assertEqual(action['res_model'], 'short.url.click')

    def test_tour_snippet(self):
        self.env['website.page'].create({
            'name': 'Share page', 'url': '/share-me', 'type': 'qweb', 'website_id': self.website.id,
            'is_published': True, 'key': 'test.share_me',
            'arch': '<t t-call="website.layout"><div id="wrap"><div class="container">'
                    '<t t-call="short_urls.s_short_url"/><t t-call="short_urls.s_short_url_qr"/></div></div></t>'})
        self.ShortUrl.create({'token': 'share', 'target_url': '/share-me', 'website_id': self.website.id})
        self.start_tour('/share-me', 'short_urls_snippet_tour')
