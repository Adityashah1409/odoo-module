"""Storage back-ends used by cloud.storage.client.

Every provider exposes the same small interface, working with POSIX-like
paths relative to the client's root (``"Partners/Azure Interior/quote.pdf"``):

    test()                    -> None, raises on failure
    mkdir(path)               -> create the folder and its parents
    upload(path, data)        -> write bytes
    download(path)            -> bytes
    delete(path)              -> remove a file or a folder (missing is fine)
    move(path, new_path)      -> rename / move
    listdir(path)             -> [{'name', 'is_dir', 'size'}]
    exists(path)              -> bool
    public_url(path)          -> link a browser can open, or None
"""
import logging
import os
import shutil
from urllib.parse import quote, unquote, urlparse

import requests
from lxml import etree

_logger = logging.getLogger(__name__)

TIMEOUT = 30


class StorageError(Exception):
    """Raised by providers; the message is stored in the sync queue/logs."""


def join_path(*parts):
    """Join path segments with '/' and drop empty segments."""
    segments = []
    for part in parts:
        if part:
            segments.extend(seg for seg in str(part).split('/') if seg)
    return '/'.join(segments)


class BaseProvider:
    def __init__(self, client):
        self.client = client

    def test(self):
        raise NotImplementedError

    def mkdir(self, path):
        raise NotImplementedError

    def upload(self, path, data):
        raise NotImplementedError

    def download(self, path):
        raise NotImplementedError

    def delete(self, path):
        raise NotImplementedError

    def move(self, path, new_path):
        raise NotImplementedError

    def listdir(self, path):
        raise NotImplementedError

    def exists(self, path):
        raise NotImplementedError

    def public_url(self, path):
        base = (self.client.browser_base_url or '').rstrip('/')
        if not base:
            return None
        return f"{base}/{quote(path)}"


def _os_errors(method):
    """Turn OSError into StorageError so the queue logs a readable message."""
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except OSError as e:
            raise StorageError(f"{method.__name__}: {e}") from e
    wrapper.__name__ = method.__name__
    return wrapper


class LocalProvider(BaseProvider):
    """A folder on the Odoo server: local disk, mounted NAS share, sync client folder."""

    def _root(self):
        root = self.client.local_path
        if not root:
            raise StorageError("No local path configured.")
        return os.path.realpath(root)

    def _abs(self, path):
        root = self._root()
        full = os.path.realpath(os.path.join(root, path))
        if full != root and not full.startswith(root + os.sep):
            raise StorageError(f"Path outside the storage root: {path}")
        return full

    @_os_errors
    def test(self):
        root = self._root()
        os.makedirs(root, exist_ok=True)
        if not os.access(root, os.W_OK):
            raise StorageError(f"Folder {root} is not writable.")

    @_os_errors
    def mkdir(self, path):
        os.makedirs(self._abs(path), exist_ok=True)

    @_os_errors
    def upload(self, path, data):
        full = self._abs(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as f:
            f.write(data or b'')

    @_os_errors
    def download(self, path):
        full = self._abs(path)
        if not os.path.isfile(full):
            raise StorageError(f"File not found: {path}")
        with open(full, 'rb') as f:
            return f.read()

    @_os_errors
    def delete(self, path):
        full = self._abs(path)
        if os.path.isdir(full):
            shutil.rmtree(full)
        elif os.path.exists(full):
            os.remove(full)

    @_os_errors
    def move(self, path, new_path):
        src, dst = self._abs(path), self._abs(new_path)
        if not os.path.exists(src):
            raise StorageError(f"Cannot move missing item: {path}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)

    @_os_errors
    def listdir(self, path):
        full = self._abs(path)
        if not os.path.isdir(full):
            return []
        result = []
        for name in sorted(os.listdir(full)):
            item = os.path.join(full, name)
            result.append({
                'name': name,
                'is_dir': os.path.isdir(item),
                'size': os.path.getsize(item) if os.path.isfile(item) else 0,
            })
        return result

    @_os_errors
    def exists(self, path):
        return os.path.exists(self._abs(path))


class WebdavProvider(BaseProvider):
    """WebDAV: Nextcloud, ownCloud, Synology, QNAP, TrueNAS, generic servers."""

    DAV_NS = {'d': 'DAV:'}

    def _url(self, path):
        base = (self.client.webdav_url or '').rstrip('/')
        if not base:
            raise StorageError("No WebDAV URL configured.")
        return f"{base}/{quote(path)}" if path else base + '/'

    def _request(self, method, path, ok=(200, 201, 204, 207), **kwargs):
        headers = kwargs.pop('headers', {})
        try:
            response = requests.request(
                method, self._url(path),
                auth=(self.client.webdav_user or '', self.client.webdav_password or ''),
                verify=self.client.verify_ssl,
                timeout=TIMEOUT,
                headers=headers,
                **kwargs,
            )
        except requests.RequestException as e:
            raise StorageError(f"{method} {path}: {e}") from e
        if response.status_code not in ok:
            raise StorageError(f"{method} {path}: HTTP {response.status_code} {response.text[:200]}")
        return response

    def test(self):
        self._request('PROPFIND', '', headers={'Depth': '0'})

    def mkdir(self, path):
        current = ''
        for segment in path.split('/'):
            if not segment:
                continue
            current = join_path(current, segment)
            # 405 = already exists
            self._request('MKCOL', current, ok=(200, 201, 405))

    def upload(self, path, data):
        parent = path.rsplit('/', 1)[0] if '/' in path else ''
        if parent:
            self.mkdir(parent)
        self._request('PUT', path, data=data or b'')

    def download(self, path):
        return self._request('GET', path, ok=(200,)).content

    def delete(self, path):
        self._request('DELETE', path, ok=(200, 204, 404))

    def move(self, path, new_path):
        parent = new_path.rsplit('/', 1)[0] if '/' in new_path else ''
        if parent:
            self.mkdir(parent)
        self._request('MOVE', path, headers={
            'Destination': self._url(new_path),
            'Overwrite': 'T',
        })

    def listdir(self, path):
        body = (b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
                b'<d:resourcetype/><d:getcontentlength/></d:prop></d:propfind>')
        response = self._request('PROPFIND', path, ok=(207, 404), data=body, headers={'Depth': '1'})
        if response.status_code == 404:
            return []
        root = etree.fromstring(response.content)
        own_path = urlparse(self._url(path)).path.rstrip('/')
        result = []
        for node in root.findall('d:response', self.DAV_NS):
            href = unquote(urlparse(node.findtext('d:href', '', self.DAV_NS)).path).rstrip('/')
            if href == unquote(own_path):
                continue
            is_dir = node.find('.//d:resourcetype/d:collection', self.DAV_NS) is not None
            size = node.findtext('.//d:getcontentlength', '0', self.DAV_NS) or '0'
            result.append({
                'name': href.rsplit('/', 1)[-1],
                'is_dir': is_dir,
                'size': int(size) if size.isdigit() else 0,
            })
        return result

    def exists(self, path):
        response = self._request('PROPFIND', path, ok=(207, 404), headers={'Depth': '0'})
        return response.status_code == 207


PROVIDERS = {
    'local': LocalProvider,
    'webdav': WebdavProvider,
}
