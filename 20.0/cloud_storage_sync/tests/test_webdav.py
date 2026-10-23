from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from ..models.providers import StorageError, WebdavProvider

PROPFIND_BODY = b"""<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response><d:href>/dav/files/odoo/Odoo/Partners/</d:href>
    <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
  <d:response><d:href>/dav/files/odoo/Odoo/Partners/Scans/</d:href>
    <d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
  <d:response><d:href>/dav/files/odoo/Odoo/Partners/quote%20v2.pdf</d:href>
    <d:propstat><d:prop><d:resourcetype/><d:getcontentlength>1234</d:getcontentlength></d:prop></d:propstat></d:response>
</d:multistatus>"""


class FakeResponse:
    def __init__(self, status_code=201, content=b''):
        self.status_code = status_code
        self.content = content
        self.text = content.decode()


@tagged('post_install', '-at_install')
class TestWebdav(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = cls.env['cloud.storage.client'].create({
            'name': 'Nextcloud', 'provider': 'webdav',
            'webdav_url': 'https://cloud.example.com/dav/files/odoo',
            'webdav_user': 'odoo', 'webdav_password': 'secret',
        })

    def test_mkdir_upload_list(self):
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs.get('headers', {})))
            if method == 'MKCOL' and url.endswith('/Odoo'):
                return FakeResponse(405)  # already exists
            if method == 'PROPFIND':
                return FakeResponse(207, PROPFIND_BODY)
            return FakeResponse(201)

        provider = WebdavProvider(self.client)
        with patch('odoo.addons.cloud_storage_sync.models.providers.requests.request', side_effect=fake_request):
            provider.upload('Odoo/Partners/quote v2.pdf', b'pdf')
            items = provider.listdir('Odoo/Partners')
            provider.move('Odoo/Partners/quote v2.pdf', 'Odoo/Archive/quote v2.pdf')

        self.assertEqual([c[0] for c in calls[:3]], ['MKCOL', 'MKCOL', 'PUT'])
        self.assertEqual(calls[2][1], 'https://cloud.example.com/dav/files/odoo/Odoo/Partners/quote%20v2.pdf')
        self.assertEqual(items, [
            {'name': 'Scans', 'is_dir': True, 'size': 0},
            {'name': 'quote v2.pdf', 'is_dir': False, 'size': 1234},
        ])
        move = [c for c in calls if c[0] == 'MOVE'][0]
        self.assertEqual(move[2]['Destination'], 'https://cloud.example.com/dav/files/odoo/Odoo/Archive/quote%20v2.pdf')

    def test_errors_raise_storage_error(self):
        provider = WebdavProvider(self.client)
        with patch('odoo.addons.cloud_storage_sync.models.providers.requests.request',
                   return_value=FakeResponse(401, b'Unauthorized')):
            with self.assertRaises(StorageError):
                provider.upload('Odoo/a.txt', b'x')

    def test_connection_failure_sets_error_state(self):
        with patch('odoo.addons.cloud_storage_sync.models.providers.requests.request',
                   return_value=FakeResponse(401, b'Unauthorized')):
            with self.assertRaises(Exception):
                self.client.action_test_connection()
