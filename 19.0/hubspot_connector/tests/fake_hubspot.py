"""In-memory HubSpot API used by the tests (patches requests.request in the client)."""
import itertools
import json
import re
from datetime import datetime, timedelta, timezone

GOOD_TOKEN = 'pat-test-good'
SINGULAR = {'contacts': 'contact', 'companies': 'company', 'deals': 'deal'}


class FakeResponse:
    def __init__(self, status, data=None, headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._data = data
        self.content = b'' if data is None else json.dumps(data).encode()
        self.text = self.content.decode()

    def json(self):
        if self._data is None:
            raise ValueError('no body')
        return self._data


class FakeHubspot:

    def __init__(self):
        self.objects = {}            # type -> {id: {...}}
        self.associations = set()    # (from_type, from_id, to_type, to_id) both directions
        self.ids = itertools.count(1001)
        self.clock = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)
        self.calls = []
        self.fail_next = []          # list of (method, path_regex, status, body)
        self.owners = [{'id': '501', 'email': 'admin@yourcompany.example.com', 'firstName': 'Mitchell', 'lastName': 'Admin'},
                       {'id': '502', 'email': 'unknown@example.com', 'firstName': 'Sam', 'lastName': 'Seller'}]
        self.pipelines = [{'id': 'default', 'label': 'Sales Pipeline', 'stages': [
            {'id': 'appointmentscheduled', 'label': 'New', 'displayOrder': 0, 'metadata': {'probability': '0.2', 'isClosed': 'false'}},
            {'id': 'qualifiedtobuy', 'label': 'Qualified', 'displayOrder': 1, 'metadata': {'probability': '0.4', 'isClosed': 'false'}},
            {'id': 'closedwon', 'label': 'Closed won', 'displayOrder': 5, 'metadata': {'probability': '1.0', 'isClosed': 'true'}},
            {'id': 'closedlost', 'label': 'Closed lost', 'displayOrder': 6, 'metadata': {'probability': '0.0', 'isClosed': 'true'}},
        ]}]

    # ------------------------------------------------------------------ helpers for tests
    def tick(self, minutes=1):
        self.clock += timedelta(minutes=minutes)
        return self.clock

    def _now(self):
        return self.tick().strftime('%Y-%m-%dT%H:%M:%S.000Z')

    def add(self, object_type, properties, associations=None):
        object_id = str(next(self.ids))
        now = self._now()
        props = {k: (str(v) if v is not None else None) for k, v in properties.items()}
        props.setdefault('lastmodifieddate' if object_type == 'contacts' else 'hs_lastmodifieddate', now)
        self.objects.setdefault(object_type, {})[object_id] = {
            'id': object_id, 'properties': props, 'createdAt': now, 'updatedAt': now, 'archived': False}
        for to_type, to_id in (associations or []):
            self.link(object_type, object_id, to_type, to_id)
        return object_id

    def change(self, object_type, object_id, **properties):
        obj = self.objects[object_type][object_id]
        now = self._now()
        obj['properties'].update({k: str(v) for k, v in properties.items()})
        obj['properties']['lastmodifieddate' if object_type == 'contacts' else 'hs_lastmodifieddate'] = now
        obj['updatedAt'] = now

    def link(self, from_type, from_id, to_type, to_id):
        self.associations.add((from_type, str(from_id), to_type, str(to_id)))
        self.associations.add((to_type, str(to_id), from_type, str(from_id)))

    def linked(self, from_type, from_id, to_type):
        return sorted(t for f, fid, tt, t in self.associations if f == from_type and fid == str(from_id) and tt == to_type)

    def get(self, object_type, object_id):
        return self.objects.get(object_type, {}).get(str(object_id))

    def all(self, object_type, archived=False):
        return [o for o in self.objects.get(object_type, {}).values() if o['archived'] == archived]

    # ------------------------------------------------------------------ fake transport
    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        path = url.split('api.hubapi.com', 1)[-1]
        self.calls.append((method, path, json))
        for index, (m, pattern, status, body) in enumerate(self.fail_next):
            if m == method and re.search(pattern, path):
                self.fail_next.pop(index)
                return FakeResponse(status, body, {'Retry-After': '1'} if status == 429 else {})
        if (headers or {}).get('Authorization') != f'Bearer {GOOD_TOKEN}':
            return FakeResponse(401, {'status': 'error', 'category': 'INVALID_AUTHENTICATION',
                                      'message': 'Authentication credentials not found.'})
        params = params or {}
        if path == '/account-info/v3/details':
            return FakeResponse(200, {'portalId': 4242, 'uiDomain': 'app-eu1.hubspot.com', 'companyCurrency': 'EUR'})
        if path == '/crm/v3/owners':
            return FakeResponse(200, {'results': self.owners})
        if path == '/crm/v3/pipelines/deals':
            return FakeResponse(200, {'results': self.pipelines})
        m = re.fullmatch(r'/crm/v4/associations/(\w+)/(\w+)/batch/read', path)
        if m:
            from_type, to_type = m.groups()
            results = []
            for item in json['inputs']:
                to = self.linked(from_type, item['id'], to_type)
                if to:
                    results.append({'from': {'id': item['id']}, 'to': [{'toObjectId': int(t), 'associationTypes': []} for t in to]})
            return FakeResponse(200, {'results': results})
        m = re.fullmatch(r'/crm/v4/objects/(\w+)/(\d+)/associations/default/(\w+)/(\d+)', path)
        if m and method == 'PUT':
            self.link(*m.groups())
            return FakeResponse(200, {'status': 'COMPLETE'})
        m = re.fullmatch(r'/crm/v3/objects/(\w+)/search', path)
        if m:
            return self._search(m.group(1), json)
        m = re.fullmatch(r'/crm/v3/objects/(\w+)/batch/read', path)
        if m:
            results = [self._public(m.group(1), self.get(m.group(1), i['id']), json.get('properties'))
                       for i in json['inputs'] if self.get(m.group(1), i['id'])]
            return FakeResponse(200, {'results': results})
        m = re.fullmatch(r'/crm/v3/objects/(\w+)', path)
        if m and method == 'GET':
            items = sorted(self.all(m.group(1)), key=lambda o: int(o['id']))
            start = int(params.get('after') or 0)
            limit = int(params.get('limit') or 100)
            page = items[start:start + limit]
            data = {'results': [self._public(m.group(1), o, params.get('properties', '').split(',')) for o in page]}
            if start + limit < len(items):
                data['paging'] = {'next': {'after': str(start + limit)}}
            return FakeResponse(200, data)
        if m and method == 'POST':
            properties = json.get('properties') or {}
            if m.group(1) == 'contacts' and properties.get('email') and any(
                    o['properties'].get('email') == properties['email'] for o in self.all('contacts')):
                return FakeResponse(409, {'status': 'error', 'category': 'CONFLICT', 'message': 'Contact already exists.'})
            object_id = self.add(m.group(1), properties)
            return FakeResponse(201, {'id': object_id, 'properties': self.get(m.group(1), object_id)['properties']})
        m = re.fullmatch(r'/crm/v3/objects/(\w+)/(\d+)', path)
        if m:
            object_type, object_id = m.groups()
            obj = self.get(object_type, object_id)
            if not obj or obj['archived']:
                return FakeResponse(404, {'status': 'error', 'category': 'OBJECT_NOT_FOUND', 'message': 'Object not found.'})
            if method == 'GET':
                data = self._public(object_type, obj, params.get('properties', '').split(','))
                if params.get('associations'):
                    data['associations'] = {t: {'results': [{'id': i, 'type': f'{SINGULAR.get(object_type, object_type)}_to_{t}'}
                                                            for i in self.linked(object_type, object_id, t)]}
                                            for t in params['associations'].split(',') if self.linked(object_type, object_id, t)}
                return FakeResponse(200, data)
            if method == 'PATCH':
                self.change(object_type, object_id, **(json.get('properties') or {}))
                return FakeResponse(200, self._public(object_type, obj, None))
            if method == 'DELETE':
                obj['archived'] = True
                return FakeResponse(204)
        return FakeResponse(404, {'status': 'error', 'message': f'Unknown route {method} {path}'})

    def _public(self, object_type, obj, properties):
        props = obj['properties'] if not properties else {k: obj['properties'].get(k) for k in properties if k}
        return {'id': obj['id'], 'properties': dict(props), 'createdAt': obj['createdAt'], 'updatedAt': obj['updatedAt'],
                'archived': obj['archived']}

    def _search(self, object_type, payload):
        items = self.all(object_type)
        for group in payload.get('filterGroups') or []:
            for f in group.get('filters') or []:
                prop, op, value = f['propertyName'], f['operator'], f['value']
                if op == 'EQ':
                    items = [o for o in items if (o['properties'].get(prop) or '') == value]
                elif op == 'GTE':
                    limit = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
                    items = [o for o in items if datetime.fromisoformat(
                        o['properties'].get(prop, o['updatedAt']).replace('Z', '+00:00')) >= limit]
        items.sort(key=lambda o: (o['updatedAt'], int(o['id'])))
        start = int(payload.get('after') or 0)
        limit = int(payload.get('limit') or 100)
        page = items[start:start + limit]
        data = {'total': len(items), 'results': [self._public(object_type, o, payload.get('properties')) for o in page]}
        if start + limit < len(items):
            data['paging'] = {'next': {'after': str(start + limit)}}
        return FakeResponse(200, data)
