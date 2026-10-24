"""Small HubSpot CRM API client (private app token), independent from the ORM."""
import base64
import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone

import requests

_logger = logging.getLogger(__name__)

BASE_URL = 'https://api.hubapi.com'
TIMEOUT = 30
PAGE_SIZE = 100
SEARCH_LIMIT = 10000  # HubSpot refuses to page a search beyond 10,000 results


class HubspotError(Exception):
    def __init__(self, message, status=None, category=None):
        super().__init__(message)
        self.status = status
        self.category = category


class HubspotSkip(Exception):
    """Nothing to do for this job (e.g. an engagement whose records are not synchronized)."""


def to_hubspot_datetime(value):
    """datetime (naive UTC) -> ISO string HubSpot accepts."""
    if not value:
        return ''
    return value.replace(tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')


def from_hubspot_datetime(value):
    """ISO string or epoch milliseconds -> naive UTC datetime (or None)."""
    if value in (None, '', False):
        return None
    text = str(value).strip()
    if text.isdigit():
        return datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc).replace(tzinfo=None)
    text = text.replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def verify_signature_v3(secret, method, uri, body, timestamp, signature, max_age=300, now=None):
    """Check a HubSpot v3 webhook signature: base64(HMAC-SHA256(secret, method + uri + body + timestamp))."""
    if not (secret and signature and timestamp):
        return False
    try:
        age = abs((now or time.time()) * 1000 - int(timestamp)) / 1000
    except (TypeError, ValueError):
        return False
    if age > max_age:
        return False
    if isinstance(body, bytes):
        body = body.decode()
    message = f'{method}{uri}{body}{timestamp}'.encode()
    expected = base64.b64encode(hmac.new(secret.encode(), message, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(expected, signature)


def _sleep(seconds):
    time.sleep(seconds)


class HubspotClient:

    def __init__(self, token, base_url=BASE_URL, max_retries=3, sleep=None):
        if not token:
            raise HubspotError('No access token configured.')
        self.token = token
        self.base_url = base_url.rstrip('/')
        self.max_retries = max_retries
        self.sleep = sleep or _sleep
        self.calls = 0

    # ------------------------------------------------------------------ transport
    def _request(self, method, path, params=None, payload=None):
        url = self.base_url + path
        headers = {'Authorization': f'Bearer {self.token}', 'Accept': 'application/json'}
        response = None
        for attempt in range(self.max_retries + 1):
            try:
                self.calls += 1
                response = requests.request(method, url, params=params, json=payload, headers=headers,
                                            timeout=TIMEOUT)
            except requests.RequestException as error:
                raise HubspotError(f'Cannot reach HubSpot: {error}') from error
            retriable = response.status_code == 429 or response.status_code >= 500
            if retriable and attempt < self.max_retries:
                try:
                    wait = float(response.headers.get('Retry-After') or 0)
                except ValueError:
                    wait = 0
                self.sleep(min(max(wait, 1 + attempt), 10))
                continue
            break
        if response.status_code == 204 or not response.content:
            if response.status_code >= 400:
                raise HubspotError(f'HubSpot answered {response.status_code}.', status=response.status_code)
            return {}
        try:
            data = response.json()
        except ValueError as error:
            raise HubspotError(f'HubSpot answered {response.status_code} with an unreadable body.',
                               status=response.status_code) from error
        if response.status_code >= 400:
            message = data.get('message') if isinstance(data, dict) else None
            raise HubspotError(message or f'HubSpot answered {response.status_code}.', status=response.status_code,
                               category=data.get('category') if isinstance(data, dict) else None)
        return data

    def get(self, path, params=None):
        return self._request('GET', path, params=params)

    def post(self, path, payload=None):
        return self._request('POST', path, payload=payload or {})

    # ------------------------------------------------------------------ account
    def account_info(self):
        return self.get('/account-info/v3/details')

    def owners(self):
        owners, after = [], None
        while True:
            data = self.get('/crm/v3/owners', {'limit': PAGE_SIZE, **({'after': after} if after else {})})
            owners += data.get('results', [])
            after = data.get('paging', {}).get('next', {}).get('after')
            if not after:
                return owners

    def pipelines(self, object_type='deals'):
        return self.get(f'/crm/v3/pipelines/{object_type}').get('results', [])

    # ------------------------------------------------------------------ objects
    def iter_objects(self, object_type, properties, modified_property=None, since=None):
        """All objects, or those modified at/after ``since`` (search, oldest change first)."""
        after = None
        seen = 0
        while True:
            if since:
                payload = {
                    'filterGroups': [{'filters': [{'propertyName': modified_property, 'operator': 'GTE',
                                                   'value': str(int(since.replace(tzinfo=timezone.utc).timestamp() * 1000))}]}],
                    'sorts': [{'propertyName': modified_property, 'direction': 'ASCENDING'}],
                    'properties': list(properties), 'limit': PAGE_SIZE,
                }
                if after:
                    payload['after'] = after
                data = self.post(f'/crm/v3/objects/{object_type}/search', payload)
            else:
                params = {'limit': PAGE_SIZE, 'properties': ','.join(properties), 'archived': 'false'}
                if after:
                    params['after'] = after
                data = self.get(f'/crm/v3/objects/{object_type}', params)
            for result in data.get('results', []):
                seen += 1
                yield result
            after = data.get('paging', {}).get('next', {}).get('after')
            if not after or (since and seen >= SEARCH_LIMIT):
                return

    def read(self, object_type, object_id, properties, associations=()):
        params = {'properties': ','.join(properties)}
        if associations:
            params['associations'] = ','.join(associations)
        return self.get(f'/crm/v3/objects/{object_type}/{object_id}', params)

    def batch_read(self, object_type, ids, properties):
        results = []
        for chunk in _chunks(list(ids), PAGE_SIZE):
            data = self.post(f'/crm/v3/objects/{object_type}/batch/read',
                             {'properties': list(properties), 'inputs': [{'id': str(i)} for i in chunk]})
            results += data.get('results', [])
        return results

    def associations(self, from_type, to_type, ids):
        """{from_id: [to_id, ...]} for the given objects."""
        mapping = {}
        for chunk in _chunks([str(i) for i in ids], PAGE_SIZE):
            data = self.post(f'/crm/v4/associations/{from_type}/{to_type}/batch/read',
                             {'inputs': [{'id': i} for i in chunk]})
            for result in data.get('results', []):
                mapping[str(result['from']['id'])] = [str(to['toObjectId']) for to in result.get('to', [])]
        return mapping

    def find(self, object_type, property_name, value, properties=()):
        """First object whose property equals value (used to avoid duplicates)."""
        if not value:
            return None
        data = self.post(f'/crm/v3/objects/{object_type}/search', {
            'filterGroups': [{'filters': [{'propertyName': property_name, 'operator': 'EQ', 'value': str(value)}]}],
            'properties': list(properties) or [property_name], 'limit': 1})
        results = data.get('results') or []
        return results[0] if results else None

    def create(self, object_type, properties):
        return str(self.post(f'/crm/v3/objects/{object_type}', {'properties': properties})['id'])

    def update(self, object_type, object_id, properties):
        return self._request('PATCH', f'/crm/v3/objects/{object_type}/{object_id}', payload={'properties': properties})

    def archive(self, object_type, object_id):
        return self._request('DELETE', f'/crm/v3/objects/{object_type}/{object_id}')

    def associate(self, from_type, from_id, to_type, to_id):
        return self._request('PUT', f'/crm/v4/objects/{from_type}/{from_id}/associations/default/{to_type}/{to_id}')


def _chunks(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]
