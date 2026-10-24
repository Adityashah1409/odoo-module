"""Mapping between HubSpot objects and Odoo records (both directions)."""
from datetime import date, datetime, time, timedelta
from urllib.parse import urlparse

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import html2plaintext, html_sanitize

from .hubspot_client import HubspotError, HubspotSkip, from_hubspot_datetime, to_hubspot_datetime

ENGAGEMENT_TARGETS = ('deals', 'contacts', 'companies')
LINE_ITEM_PROPERTIES = ['name', 'quantity', 'price', 'hs_product_id', 'hs_discount_percentage']

SPECS = {
    'companies': {
        'model': 'res.partner', 'modified': 'hs_lastmodifieddate', 'associations': [],
        'properties': ['name', 'domain', 'website', 'phone', 'address', 'city', 'zip', 'state', 'country',
                       'description', 'hubspot_owner_id'],
    },
    'contacts': {
        'model': 'res.partner', 'modified': 'lastmodifieddate', 'associations': ['companies'],
        'properties': ['firstname', 'lastname', 'email', 'phone', 'mobilephone', 'jobtitle', 'address', 'city', 'zip',
                       'state', 'country', 'website', 'hubspot_owner_id'],
    },
    'products': {
        'model': 'product.template', 'modified': 'hs_lastmodifieddate', 'associations': [],
        'properties': ['name', 'price', 'hs_sku', 'description', 'hs_cost_of_goods_sold'],
    },
    'deals': {
        'model': 'crm.lead', 'modified': 'hs_lastmodifieddate', 'associations': ['contacts', 'companies'],
        'properties': ['dealname', 'amount', 'closedate', 'dealstage', 'pipeline', 'hubspot_owner_id', 'description'],
    },
    'quotes': {
        'model': 'sale.order', 'modified': 'hs_lastmodifieddate',
        'associations': ['contacts', 'companies', 'deals', 'line_items'],
        'properties': ['hs_title', 'hs_expiration_date', 'hs_status', 'hs_currency'],
    },
    'invoices': {
        'model': 'account.move', 'modified': 'hs_lastmodifieddate',
        'associations': ['contacts', 'companies', 'line_items'],
        'properties': ['hs_number', 'hs_invoice_date', 'hs_due_date', 'hs_currency', 'hs_invoice_status'],
    },
    'notes': {
        'model': 'mail.message', 'modified': 'hs_lastmodifieddate', 'associations': list(ENGAGEMENT_TARGETS),
        'properties': ['hs_note_body', 'hs_timestamp', 'hubspot_owner_id'],
    },
    'tasks': {
        'model': 'mail.activity', 'modified': 'hs_lastmodifieddate', 'associations': list(ENGAGEMENT_TARGETS),
        'properties': ['hs_task_subject', 'hs_task_body', 'hs_task_status', 'hs_task_priority', 'hs_timestamp',
                       'hubspot_owner_id'],
    },
    'meetings': {
        'model': 'calendar.event', 'modified': 'hs_lastmodifieddate', 'associations': list(ENGAGEMENT_TARGETS),
        'properties': ['hs_meeting_title', 'hs_meeting_body', 'hs_meeting_start_time', 'hs_meeting_end_time',
                       'hs_meeting_location', 'hs_timestamp', 'hubspot_owner_id'],
    },
    'emails': {
        'model': 'mail.message', 'modified': 'hs_lastmodifieddate', 'associations': list(ENGAGEMENT_TARGETS),
        'properties': ['hs_email_subject', 'hs_email_text', 'hs_email_html', 'hs_email_direction', 'hs_timestamp'],
    },
}


def _domain_of(website):
    if not website:
        return ''
    url = website if '//' in website else f'//{website}'
    host = (urlparse(url).hostname or '').lower()
    return host[4:] if host.startswith('www.') else host


def _float(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _date(value):
    parsed = from_hubspot_datetime(value)
    if parsed:
        return parsed.date()
    try:
        return date.fromisoformat(str(value)[:10]) if value else False
    except ValueError:
        return False


class HubspotSync(models.AbstractModel):
    _name = 'hubspot.sync'
    _description = 'HubSpot synchronization engine'

    # ------------------------------------------------------------------ specs & helpers
    @api.model
    def _spec(self, object_type):
        return SPECS[object_type]

    @api.model
    def _mappings(self, account, object_type, direction):
        return account.mapping_ids.filtered(
            lambda m: m.active and m.object_type == object_type and m.direction in ('both', direction))

    @api.model
    def _import_properties(self, account, object_type):
        spec = SPECS[object_type]
        properties = spec['properties'] + [spec['modified']] + \
            self._mappings(account, object_type, 'import').mapped('hubspot_property')
        return list(dict.fromkeys(properties))

    def _link_model(self):
        return self.env['hubspot.record']

    @api.model
    def _user(self, account, owner_id):
        if not owner_id:
            return self.env['res.users']
        return account.owner_ids.filtered(lambda o: o.hubspot_id == str(owner_id)).user_id

    @api.model
    def _owner(self, account, user):
        if not user:
            return ''
        return account.owner_ids.filtered(lambda o: o.user_id == user)[:1].hubspot_id or ''

    @api.model
    def _country(self, value):
        if not value:
            return self.env['res.country']
        Country = self.env['res.country']
        return Country.search([('code', '=ilike', value)], limit=1) or Country.search([('name', '=ilike', value)], limit=1)

    @api.model
    def _state(self, country, value):
        if not (country and value):
            return self.env['res.country.state']
        State = self.env['res.country.state']
        domain = [('country_id', '=', country.id)]
        return State.search(domain + [('code', '=ilike', value)], limit=1) or \
            State.search(domain + [('name', '=ilike', value)], limit=1)

    @api.model
    def _write_changed(self, record, vals):
        """Write only what differs, so unchanged imports do not touch write_date (and are not exported back)."""
        changed = {}
        for name, value in vals.items():
            field = record._fields[name]
            current = record[name]
            if field.type == 'many2one':
                current = current.id
                value = value or False
            elif field.type in ('one2many', 'many2many'):
                changed[name] = value
                continue
            elif field.type in ('char', 'text', 'html', 'selection'):
                current = current or False
                value = value or False
                if field.type == 'html':
                    current = html2plaintext(current or '').strip() or False
                    compare = html2plaintext(value or '').strip() or False
                    if current != compare:
                        changed[name] = value
                    continue
            elif field.type in ('float', 'monetary'):
                if abs((current or 0.0) - (value or 0.0)) > 1e-6:
                    changed[name] = value
                continue
            if current != value:
                changed[name] = value
        if changed:
            record.write(changed)
        return bool(changed)

    @api.model
    def _result(self, changed):
        return 'updated' if changed else 'unchanged'

    @api.model
    def _to_odoo(self, record_model, field_name, value):
        field = self.env[record_model]._fields[field_name]
        if value in (None, ''):
            return False if field.type not in ('integer', 'float', 'monetary') else 0
        if field.type in ('char', 'text', 'html'):
            return str(value)
        if field.type == 'integer':
            return int(_float(value))
        if field.type in ('float', 'monetary'):
            return _float(value)
        if field.type == 'boolean':
            return str(value).lower() in ('true', '1', 'yes')
        if field.type == 'date':
            return _date(value)
        if field.type == 'datetime':
            return from_hubspot_datetime(value) or False
        if field.type == 'selection':
            keys = [key for key, _label in field._description_selection(self.env)]
            return value if value in keys else False
        if field.type == 'many2one':
            return self.env[field.comodel_name].search([('display_name', '=ilike', str(value))], limit=1).id or False
        return False

    @api.model
    def _to_hubspot(self, record, field_name):
        field = record._fields[field_name]
        value = record[field_name]
        if field.type == 'many2one':
            return value.display_name or ''
        if field.type == 'boolean':
            return 'true' if value else 'false'
        if field.type == 'date':
            return value.isoformat() if value else ''
        if field.type == 'datetime':
            return to_hubspot_datetime(value)
        if field.type == 'html':
            return str(value or '')
        if value is False or value is None:
            return ''
        return value

    @api.model
    def _mapped_import_values(self, account, object_type, model, properties):
        return {m.field_id.name: self._to_odoo(model, m.field_id.name, properties.get(m.hubspot_property))
                for m in self._mappings(account, object_type, 'import') if m.hubspot_property in properties}

    @api.model
    def _mapped_export_values(self, account, object_type, record):
        return {m.hubspot_property: self._to_hubspot(record, m.field_id.name)
                for m in self._mappings(account, object_type, 'export')}

    # ------------------------------------------------------------------ jobs
    @api.model
    def _read_object(self, account, object_type, hubspot_id):
        try:
            data = account._client().read(object_type, hubspot_id, self._import_properties(account, object_type),
                                          SPECS[object_type]['associations'])
        except HubspotError as error:
            if error.status == 404:
                raise HubspotSkip(self.env._('%(type)s %(id)s no longer exists in HubSpot.',
                                             type=object_type, id=hubspot_id)) from error
            raise
        associations = {}
        for to_type, value in (data.get('associations') or {}).items():
            key = to_type.replace(' ', '_')
            associations[key] = [str(r['id']) for r in value.get('results', [])]
        return {'id': str(data['id']), 'properties': data.get('properties') or {}, 'associations': associations}

    @api.model
    def _import_job(self, job):
        data = job.payload or self._read_object(job.account_id, job.object_type, job.hubspot_id)
        return self._import_data(job.account_id, job.object_type, data)

    @api.model
    def _import_data(self, account, object_type, data):
        Link = self._link_model()
        link = Link._get(account, object_type, hubspot_id=data['id'])
        record = link._record() if link else None
        if link and not record:
            link.unlink()
            link = None
        if record and account.conflict_policy == 'odoo' and link.fingerprint and \
                Link._fingerprint(self._safe_export_properties(account, object_type, record)) != link.fingerprint:
            return record, 'unchanged'  # changed in Odoo since the last sync: Odoo wins, the export sends it
        handler = getattr(self, f'_import_{object_type}')
        record, result = handler(account, data, record)
        Link._set(account, object_type, data['id'], record, self._safe_export_properties(account, object_type, record))
        return record, result

    @api.model
    def _ensure_imported(self, account, object_type, hubspot_id):
        """Odoo record of a HubSpot object, importing it now if needed (associations)."""
        if not hubspot_id:
            return None
        link = self._link_model()._get(account, object_type, hubspot_id=hubspot_id)
        record = link._record() if link else None
        if record:
            return record
        if self.env.context.get('hubspot_depth', 0) > 3:
            return None
        data = self.with_context(hubspot_depth=self.env.context.get('hubspot_depth', 0) + 1)._read_object(
            account, object_type, hubspot_id)
        return self.with_context(hubspot_depth=self.env.context.get('hubspot_depth', 0) + 1)._import_data(
            account, object_type, data)[0]

    @api.model
    def _delete_job(self, job):
        link = self._link_model()._get(job.account_id, job.object_type, hubspot_id=job.hubspot_id)
        if not link:
            raise HubspotSkip(self.env._('Not linked to an Odoo record.'))
        record = link._record()
        link.unlink()
        if record and 'active' in record._fields:
            record.active = False
            return record, 'archived'
        return record, 'unchanged'

    @api.model
    def _safe_export_properties(self, account, object_type, record):
        try:
            return self._export_properties(account, object_type, record)
        except (UserError, HubspotSkip, HubspotError):
            return {}

    @api.model
    def _export_properties(self, account, object_type, record):
        properties = getattr(self, f'_export_{object_type}')(account, record)
        properties.update(self._mapped_export_values(account, object_type, record))
        return properties

    @api.model
    def _export_job(self, job):
        record = job._record()
        if not record:
            raise HubspotSkip(self.env._('The Odoo record no longer exists.'))
        return self._export_record(job.account_id, job.object_type, record)

    @api.model
    def _export_record(self, account, object_type, record):
        Link = self._link_model()
        properties = self._export_properties(account, object_type, record)
        link = Link._get(account, object_type, record=record)
        if link and link.fingerprint == Link._fingerprint(properties):
            return record, 'unchanged'
        client = account._client()
        result = 'updated'
        hubspot_id = link.hubspot_id if link else None
        sent = {key: value for key, value in properties.items() if not key.startswith('_')}
        if hubspot_id:
            try:
                client.update(object_type, hubspot_id, sent)
            except HubspotError as error:
                if error.status != 404:
                    raise
                link.unlink()  # deleted in HubSpot: create it again
                link, hubspot_id = None, None
        if not hubspot_id:
            existing = self._find_in_hubspot(account, object_type, record, sent)
            if existing:
                hubspot_id = str(existing['id'])
                client.update(object_type, hubspot_id, sent)
            else:
                hubspot_id = client.create(object_type, sent)
                result = 'created'
        link = Link._set(account, object_type, hubspot_id, record, properties)
        after = getattr(self, f'_after_export_{object_type}', None)
        if after:
            after(account, record, hubspot_id, link)
        return record, result

    @api.model
    def _ensure_exported(self, account, object_type, record):
        """HubSpot id of an Odoo record, exporting it now when that object is exported."""
        if not record:
            return None
        link = self._link_model()._get(account, object_type, record=record)
        if link:
            return link.hubspot_id
        obj = account.object_ids.filtered(lambda o: o.object_type == object_type)
        if not obj.export_enabled:
            return None
        self._export_record(account, object_type, record)
        return self._link_model()._get(account, object_type, record=record).hubspot_id

    @api.model
    def _find_in_hubspot(self, account, object_type, record, properties):
        keys = {'contacts': 'email', 'companies': 'domain', 'products': 'hs_sku'}
        key = keys.get(object_type)
        if not key or not properties.get(key):
            return None
        found = account._client().find(object_type, key, properties[key])
        if found and self._link_model()._get(account, object_type, hubspot_id=found['id']):
            return None  # already linked to another record: do not merge two Odoo records
        return found

    # ------------------------------------------------------------------ export scope
    @api.model
    def _linked_ids(self, account, object_type):
        return self._link_model().search([('account_id', '=', account.id),
                                          ('object_type', '=', object_type)]).mapped('res_id')

    @api.model
    def _excluded_partner_ids(self):
        users = self.env['res.users'].with_context(active_test=False).search([('share', '=', False)])
        return (users.partner_id | self.env['res.company'].sudo().search([]).partner_id).ids

    @api.model
    def _export_domain(self, account, object_type):
        company_domain = [('company_id', 'in', [False, account.company_id.id])]
        if object_type == 'companies':
            return [('parent_id', '=', False), ('active', '=', True), ('id', 'not in', self._excluded_partner_ids()),
                    '|', '|', ('is_company', '=', True), ('child_ids', '!=', False),
                    ('id', 'in', self._linked_ids(account, 'companies'))] + company_domain
        if object_type == 'contacts':
            return [('active', '=', True), ('email', '!=', False), ('is_company', '=', False),
                    ('child_ids', '=', False), ('id', 'not in', self._excluded_partner_ids()),
                    ('id', 'not in', self._linked_ids(account, 'companies'))] + company_domain
        if object_type == 'products':
            return [('sale_ok', '=', True), ('active', '=', True)] + company_domain
        if object_type == 'deals':
            return [('type', '=', account.deal_type)] + company_domain
        if object_type == 'quotes':
            return [('company_id', '=', account.company_id.id), ('state', 'in', ('draft', 'sent', 'sale', 'cancel'))]
        if object_type == 'invoices':
            return [('company_id', '=', account.company_id.id), ('move_type', '=', 'out_invoice')]
        if object_type in ('notes', 'emails'):
            subtype = 'mail.mt_note' if object_type == 'notes' else 'mail.mt_comment'
            types = ('comment',) if object_type == 'notes' else ('comment', 'email')
            return [('model', 'in', ('res.partner', 'crm.lead')), ('message_type', 'in', types),
                    ('subtype_id', '=', self.env['ir.model.data']._xmlid_to_res_id(subtype))]
        if object_type == 'tasks':
            return [('res_model', 'in', ('res.partner', 'crm.lead'))]
        if object_type == 'meetings':
            return [('partner_ids', 'in', self._linked_ids(account, 'contacts'))]
        return [('id', '=', 0)]

    @api.model
    def _export_filter(self, account, object_type, records):
        """Engagements are exported only for synchronized records."""
        if object_type in ('notes', 'emails', 'tasks'):
            return records.filtered(lambda r: self._engagement_target_link(account, r))
        return records

    # ------------------------------------------------------------------ partners
    def _address_values(self, properties):
        country = self._country(properties.get('country'))
        return {
            'street': properties.get('address') or False,
            'city': properties.get('city') or False,
            'zip': properties.get('zip') or False,
            'country_id': country.id or False,
            'state_id': self._state(country, properties.get('state')).id or False,
        }

    def _address_properties(self, partner):
        return {'address': partner.street or '', 'city': partner.city or '', 'zip': partner.zip or '',
                'state': partner.state_id.name or '', 'country': partner.country_id.name or ''}

    def _import_companies(self, account, data, record):
        p = data['properties']
        domain = p.get('domain') or _domain_of(p.get('website'))
        vals = {
            'name': p.get('name') or domain or self.env._('HubSpot company %s', data['id']),
            'website': p.get('website') or (f'https://{domain}' if domain else False),
            'phone': p.get('phone') or False,
            'is_company': True,
            **self._address_values(p),
            **self._mapped_import_values(account, 'companies', 'res.partner', p),
        }
        if p.get('description'):
            vals['comment'] = Markup('<p>%s</p>') % p['description']
        user = self._user(account, p.get('hubspot_owner_id'))
        if user:
            vals['user_id'] = user.id
        Partner = self.env['res.partner']
        if not record and domain:
            record = Partner.search([('parent_id', '=', False), ('website', 'ilike', domain),
                                     ('id', 'not in', self._linked_ids(account, 'companies'))], limit=1)
        if not record:
            record = Partner.search([('parent_id', '=', False), ('name', '=ilike', vals['name']),
                                     ('id', 'not in', self._linked_ids(account, 'companies'))], limit=1)
        if record:
            return record, self._result(self._write_changed(record, vals))
        return Partner.create(vals), 'created'

    def _export_companies(self, account, partner):
        return {
            'name': partner.name or '',
            'domain': _domain_of(partner.website),
            'phone': partner.phone or '',
            **self._address_properties(partner),
            'hubspot_owner_id': self._owner(account, partner.user_id),
        }

    def _import_contacts(self, account, data, record):
        p = data['properties']
        name = ' '.join(filter(None, [p.get('firstname'), p.get('lastname')])) or p.get('email') or \
            self.env._('HubSpot contact %s', data['id'])
        vals = {
            'name': name,
            'email': p.get('email') or False,
            'phone': p.get('phone') or p.get('mobilephone') or False,
            'function': p.get('jobtitle') or False,
            **self._address_values(p),
            **self._mapped_import_values(account, 'contacts', 'res.partner', p),
        }
        if p.get('website'):
            vals['website'] = p['website']
        user = self._user(account, p.get('hubspot_owner_id'))
        if user:
            vals['user_id'] = user.id
        company_ids = (data.get('associations') or {}).get('companies') or []
        company = self._ensure_imported(account, 'companies', company_ids[0]) if company_ids else None
        if company:
            vals['parent_id'] = company.id
        Partner = self.env['res.partner']
        if not record and p.get('email'):
            record = Partner.search([('email', '=ilike', p['email']), ('is_company', '=', False),
                                     ('id', 'not in', self._linked_ids(account, 'contacts'))], limit=1)
        if record:
            return record, self._result(self._write_changed(record, vals))
        return Partner.create(vals), 'created'

    def _export_contacts(self, account, partner):
        first, _sep, last = (partner.name or '').strip().partition(' ')
        return {
            'firstname': first, 'lastname': last, 'email': partner.email or '', 'phone': partner.phone or '',
            'jobtitle': partner.function or '', **self._address_properties(partner),
            'hubspot_owner_id': self._owner(account, partner.user_id),
        }

    def _after_export_contacts(self, account, partner, hubspot_id, link):
        company = partner.parent_id.commercial_partner_id if partner.parent_id else None
        company_id = self._ensure_exported(account, 'companies', company)
        if company_id and (link.extra or {}).get('company') != company_id:
            account._client().associate('contacts', hubspot_id, 'companies', company_id)
            link.extra = dict(link.extra or {}, company=company_id)

    def _partner_link(self, account, partner):
        Link = self._link_model()
        for object_type in ('contacts', 'companies'):
            link = Link._get(account, object_type, record=partner)
            if link:
                return link
        return Link

    # ------------------------------------------------------------------ products
    def _import_products(self, account, data, record):
        p = data['properties']
        vals = {
            'name': p.get('name') or self.env._('HubSpot product %s', data['id']),
            'list_price': _float(p.get('price')),
            'default_code': p.get('hs_sku') or False,
            'description_sale': p.get('description') or False,
            'standard_price': _float(p.get('hs_cost_of_goods_sold')),
            **self._mapped_import_values(account, 'products', 'product.template', p),
        }
        Template = self.env['product.template']
        if not record and p.get('hs_sku'):
            record = Template.search([('default_code', '=', p['hs_sku']),
                                      ('id', 'not in', self._linked_ids(account, 'products'))], limit=1)
        if record:
            return record, self._result(self._write_changed(record, vals))
        return Template.create(vals), 'created'

    def _export_products(self, account, template):
        return {'name': template.name or '', 'price': template.list_price, 'hs_sku': template.default_code or '',
                'description': template.description_sale or '', 'hs_cost_of_goods_sold': template.standard_price}

    # ------------------------------------------------------------------ deals
    def _import_deals(self, account, data, record):
        p = data['properties']
        assoc = data.get('associations') or {}
        vals = {
            'name': p.get('dealname') or self.env._('HubSpot deal %s', data['id']),
            'type': account.deal_type,
            'expected_revenue': _float(p.get('amount')),
            'date_deadline': _date(p.get('closedate')),
            'company_id': account.company_id.id,
            **self._mapped_import_values(account, 'deals', 'crm.lead', p),
        }
        if p.get('description'):
            vals['description'] = Markup('<p>%s</p>') % p['description']
        user = self._user(account, p.get('hubspot_owner_id'))
        if user:
            vals['user_id'] = user.id
        contact = self._ensure_imported(account, 'contacts', (assoc.get('contacts') or [None])[0])
        company = self._ensure_imported(account, 'companies', (assoc.get('companies') or [None])[0])
        if contact or company:
            vals['partner_id'] = (contact or company).id
        stage = account.stage_ids.filtered(
            lambda s: s.hubspot_id == p.get('dealstage') and (not p.get('pipeline') or s.pipeline_id == p['pipeline']))[:1]
        if stage.is_closed and not stage.is_won:
            vals.update(active=False, probability=0)
            current = record.stage_id if record else self.env['crm.stage']
            if not current or current.is_won:
                # a lead cannot be lost in a won stage
                not_won = stage.crm_stage_id if stage.crm_stage_id and not stage.crm_stage_id.is_won else \
                    self.env['crm.stage'].search([('is_won', '=', False)], limit=1)
                if not_won:
                    vals['stage_id'] = not_won.id
        else:
            vals['active'] = True
            crm_stage = stage.crm_stage_id
            if stage.is_won and not crm_stage.is_won:
                crm_stage = self.env['crm.stage'].search([('is_won', '=', True)], limit=1)
            if crm_stage:
                vals['stage_id'] = crm_stage.id
        Lead = self.env['crm.lead'].with_context(active_test=False, mail_create_nosubscribe=True)
        if record:
            return record, self._result(self._write_changed(record, vals))
        return Lead.create(vals), 'created'

    def _export_deals(self, account, lead):
        stages = account.stage_ids.filtered(lambda s: s.pipeline_id == (account.pipeline_id or 'default'))
        if not stages:
            raise UserError(self.env._('Fetch the HubSpot pipelines first (HubSpot account > Fetch owners & stages).'))
        if not lead.active and not lead.probability:
            stage = stages.filtered(lambda s: s.is_closed and not s.is_won)[:1]
        elif lead.stage_id.is_won:
            stage = stages.filtered('is_won')[:1]
        else:
            stage = stages.filtered(lambda s: s.crm_stage_id == lead.stage_id)[:1] or \
                stages.filtered(lambda s: not s.is_closed).sorted('sequence')[:1]
        return {
            'dealname': lead.name or '', 'amount': lead.expected_revenue,
            'closedate': lead.date_deadline.isoformat() if lead.date_deadline else '',
            'pipeline': account.pipeline_id or 'default', 'dealstage': stage.hubspot_id or '',
            'hubspot_owner_id': self._owner(account, lead.user_id),
        }

    def _after_export_deals(self, account, lead, hubspot_id, link):
        partner = lead.partner_id
        done = dict(link.extra or {})
        client = account._client()
        if partner:
            company = partner.commercial_partner_id
            contact = partner if partner != company else None
            for object_type, target in (('contacts', contact), ('companies', company)):
                target_id = self._ensure_exported(account, object_type, target) if target else None
                if target_id and done.get(object_type) != target_id:
                    client.associate('deals', hubspot_id, object_type, target_id)
                    done[object_type] = target_id
        link.extra = done

    # ------------------------------------------------------------------ quotes & invoices
    def _line_values(self, account, data):
        ids = (data.get('associations') or {}).get('line_items') or []
        if not ids:
            return []
        lines = []
        for item in account._client().batch_read('line_items', ids, LINE_ITEM_PROPERTIES):
            p = item.get('properties') or {}
            template = self._ensure_imported(account, 'products', p.get('hs_product_id')) if p.get('hs_product_id') else None
            product = template.product_variant_id if template else self._fallback_product(account)
            lines.append({'product_id': product.id, 'name': p.get('name') or product.display_name,
                          'quantity': _float(p.get('quantity')) or 1.0, 'price_unit': _float(p.get('price')),
                          'discount': _float(p.get('hs_discount_percentage'))})
        return lines

    def _fallback_product(self, account):
        if not account.fallback_product_id:
            account.fallback_product_id = self.env['product.product'].create({
                'name': self.env._('HubSpot line item'), 'type': 'service', 'sale_ok': True, 'list_price': 0.0})
        return account.fallback_product_id

    def _customer(self, account, data):
        assoc = data.get('associations') or {}
        for object_type in ('contacts', 'companies'):
            ids = assoc.get(object_type) or []
            if ids:
                partner = self._ensure_imported(account, object_type, ids[0])
                if partner:
                    return partner
        deal = self._ensure_imported(account, 'deals', (assoc.get('deals') or [None])[0])
        if deal and deal.partner_id:
            return deal.partner_id
        raise UserError(self.env._('The HubSpot object has no associated contact or company.'))

    def _import_quotes(self, account, data, record):
        p = data['properties']
        partner = self._customer(account, data)
        lines = self._line_values(account, data)
        vals = {'partner_id': partner.id, 'client_order_ref': p.get('hs_title') or False,
                'validity_date': _date(p.get('hs_expiration_date')), 'company_id': account.company_id.id,
                **self._mapped_import_values(account, 'quotes', 'sale.order', p)}
        line_cmds = [(0, 0, {'product_id': ln['product_id'], 'name': ln['name'], 'product_uom_qty': ln['quantity'],
                             'price_unit': ln['price_unit'], 'discount': ln['discount']}) for ln in lines]
        if record:
            if record.state not in ('draft', 'sent'):
                return record, 'unchanged'
            changed = self._write_changed(record, vals)
            current = [(ln.product_id.id, ln.product_uom_qty, ln.price_unit, ln.discount) for ln in record.order_line
                       if not ln.display_type]
            wanted = [(c[2]['product_id'], c[2]['product_uom_qty'], c[2]['price_unit'], c[2]['discount']) for c in line_cmds]
            if current != wanted:
                record.order_line = [(5, 0, 0)] + line_cmds
                changed = True
            return record, self._result(changed)
        return self.env['sale.order'].create({**vals, 'order_line': line_cmds}), 'created'

    def _export_quotes(self, account, order):
        status = {'draft': 'DRAFT', 'sent': 'DRAFT', 'sale': 'APPROVED', 'cancel': 'REJECTED'}.get(order.state, 'DRAFT')
        expiration = order.validity_date or (order.date_order.date() + timedelta(days=30))
        lines = [(ln.name, ln.product_uom_qty, ln.price_unit, ln.discount, ln.product_id.id)
                 for ln in order.order_line if not ln.display_type]
        return {'hs_title': order.client_order_ref or order.name, 'hs_expiration_date': expiration.isoformat(),
                'hs_status': status, 'hs_currency': order.currency_id.name,
                # not sent: changes in the lines must trigger an export
                '_lines': repr(lines)}

    def _import_invoices(self, account, data, record):
        p = data['properties']
        partner = self._customer(account, data)
        lines = self._line_values(account, data)
        vals = {'partner_id': partner.id, 'ref': p.get('hs_number') or False,
                'invoice_date': _date(p.get('hs_invoice_date')), 'invoice_date_due': _date(p.get('hs_due_date')),
                **self._mapped_import_values(account, 'invoices', 'account.move', p)}
        line_cmds = [(0, 0, {'product_id': ln['product_id'], 'name': ln['name'], 'quantity': ln['quantity'],
                             'price_unit': ln['price_unit'], 'discount': ln['discount']}) for ln in lines]
        if record:
            if record.state != 'draft':
                return record, 'unchanged'
            changed = self._write_changed(record, vals)
            current = [(ln.product_id.id, ln.quantity, ln.price_unit, ln.discount) for ln in record.invoice_line_ids]
            wanted = [(c[2]['product_id'], c[2]['quantity'], c[2]['price_unit'], c[2]['discount']) for c in line_cmds]
            if current != wanted:
                record.invoice_line_ids = [(5, 0, 0)] + line_cmds
                changed = True
            return record, self._result(changed)
        move = self.env['account.move'].with_company(account.company_id).create({
            **vals, 'move_type': 'out_invoice', 'invoice_line_ids': line_cmds})
        return move, 'created'

    def _export_invoices(self, account, move):
        if move.state == 'cancel':
            status = 'voided'
        elif move.state == 'draft':
            status = 'draft'
        elif move.payment_state in ('paid', 'in_payment'):
            status = 'paid'
        else:
            status = 'open'
        lines = [(ln.name, ln.quantity, ln.price_unit, ln.discount, ln.product_id.id) for ln in move.invoice_line_ids]
        return {'hs_currency': move.currency_id.name,
                'hs_invoice_date': move.invoice_date.isoformat() if move.invoice_date else '',
                'hs_due_date': move.invoice_date_due.isoformat() if move.invoice_date_due else '',
                'hs_invoice_status': status, '_lines': repr(lines)}

    def _after_export_document(self, account, record, hubspot_id, link, object_type, lines):
        client = account._client()
        extra = dict(link.extra or {})
        partner = record.partner_id
        company = partner.commercial_partner_id
        for target_type, target in (('contacts', partner if partner != company else None), ('companies', company)):
            target_id = self._ensure_exported(account, target_type, target) if target else None
            if target_id and extra.get(target_type) != target_id:
                client.associate(object_type, hubspot_id, target_type, target_id)
                extra[target_type] = target_id
        signature = repr([(ln['name'], ln['quantity'], ln['price'], ln['hs_discount_percentage'], ln.get('hs_product_id'))
                          for ln in lines])
        if extra.get('lines_signature') != signature:
            for old_id in extra.get('line_items', []):
                try:
                    client.archive('line_items', old_id)
                except HubspotError as error:
                    if error.status != 404:
                        raise
            new_ids = []
            for properties in lines:
                line_id = client.create('line_items', {k: v for k, v in properties.items() if v not in (None, '')})
                client.associate('line_items', line_id, object_type, hubspot_id)
                new_ids.append(line_id)
            extra.update(line_items=new_ids, lines_signature=signature)
        link.extra = extra

    def _line_item_properties(self, account, product, name, quantity, price, discount):
        template = product.product_tmpl_id
        product_id = self._ensure_exported(account, 'products', template) if template else None
        return {'name': name or product.display_name or '', 'quantity': quantity, 'price': price,
                'hs_discount_percentage': discount or 0, 'hs_product_id': product_id or None}

    def _after_export_quotes(self, account, order, hubspot_id, link):
        lines = [self._line_item_properties(account, ln.product_id, ln.name, ln.product_uom_qty, ln.price_unit,
                                            ln.discount) for ln in order.order_line if not ln.display_type]
        self._after_export_document(account, order, hubspot_id, link, 'quotes', lines)
        if 'opportunity_id' in order._fields and order.opportunity_id:
            deal = self._link_model()._get(account, 'deals', record=order.opportunity_id)
            if deal and (link.extra or {}).get('deal') != deal.hubspot_id:
                account._client().associate('quotes', hubspot_id, 'deals', deal.hubspot_id)
                link.extra = dict(link.extra or {}, deal=deal.hubspot_id)

    def _after_export_invoices(self, account, move, hubspot_id, link):
        lines = [self._line_item_properties(account, ln.product_id, ln.name, ln.quantity, ln.price_unit, ln.discount)
                 for ln in move.invoice_line_ids]
        self._after_export_document(account, move, hubspot_id, link, 'invoices', lines)

    # ------------------------------------------------------------------ engagements
    def _engagement_target(self, account, data):
        """Odoo record an engagement belongs to: the deal first, then the contact, then the company."""
        assoc = data.get('associations') or {}
        for object_type in ENGAGEMENT_TARGETS:
            for hubspot_id in assoc.get(object_type) or []:
                link = self._link_model()._get(account, object_type, hubspot_id=hubspot_id)
                record = link._record() if link else None
                if not record and account.object_ids.filtered(
                        lambda o: o.object_type == object_type and o.import_enabled):
                    record = self._ensure_imported(account, object_type, hubspot_id)
                if record:
                    return record
        raise HubspotSkip(self.env._('None of the associated records is synchronized with Odoo.'))

    def _engagement_target_link(self, account, record):
        model = record.model if record._name == 'mail.message' else record.res_model
        res_id = record.res_id
        if model == 'crm.lead':
            return self._link_model().search([('account_id', '=', account.id), ('object_type', '=', 'deals'),
                                              ('res_model', '=', 'crm.lead'), ('res_id', '=', res_id)], limit=1)
        if model == 'res.partner':
            return self._partner_link(account, self.env['res.partner'].browse(res_id))
        return self._link_model()

    def _author(self, account, owner_id):
        user = self._user(account, owner_id)
        return user.partner_id if user else self.env.user.partner_id

    def _import_notes(self, account, data, record):
        p = data['properties']
        body = Markup(html_sanitize(p.get('hs_note_body') or ''))
        when = from_hubspot_datetime(p.get('hs_timestamp')) or fields.Datetime.now()
        if record:
            return record, self._result(self._write_changed(record.sudo(), {'body': body, 'date': when}))
        target = self._engagement_target(account, data)
        message = target.with_context(mail_create_nosubscribe=True).message_post(
            body=body, message_type='comment', subtype_xmlid='mail.mt_note',
            author_id=self._author(account, p.get('hubspot_owner_id')).id)
        message.sudo().date = when
        return message, 'created'

    def _export_notes(self, account, message):
        return {'hs_note_body': str(message.body or ''), 'hs_timestamp': to_hubspot_datetime(message.date),
                'hubspot_owner_id': self._owner(account, message.author_id.user_ids[:1])}

    def _import_emails(self, account, data, record):
        p = data['properties']
        html = p.get('hs_email_html') or (Markup('<p>%s</p>') % (p.get('hs_email_text') or ''))
        body = Markup(html_sanitize(html))
        when = from_hubspot_datetime(p.get('hs_timestamp')) or fields.Datetime.now()
        subject = p.get('hs_email_subject') or False
        if record:
            return record, self._result(self._write_changed(record.sudo(), {'body': body, 'subject': subject, 'date': when}))
        target = self._engagement_target(account, data)
        incoming = p.get('hs_email_direction') == 'INCOMING_EMAIL'
        author = target.partner_id if incoming and 'partner_id' in target._fields and target.partner_id else \
            (target if incoming and target._name == 'res.partner' else self.env.user.partner_id)
        message = target._message_log(body=body, subject=subject, author_id=author.id, message_type='email')
        message.sudo().date = when
        return message, 'created'

    def _export_emails(self, account, message):
        internal = any(not user.share for user in message.author_id.user_ids)
        return {'hs_email_subject': message.subject or message.record_name or '',
                'hs_email_html': str(message.body or ''),
                'hs_email_direction': 'EMAIL' if internal else 'INCOMING_EMAIL',
                'hs_email_status': 'SENT', 'hs_timestamp': to_hubspot_datetime(message.date)}

    def _import_tasks(self, account, data, record):
        p = data['properties']
        due = from_hubspot_datetime(p.get('hs_timestamp'))
        user = self._user(account, p.get('hubspot_owner_id')) or account.default_user_id or self.env.user
        vals = {'summary': p.get('hs_task_subject') or self.env._('HubSpot task'),
                'note': Markup(html_sanitize(p.get('hs_task_body') or '')),
                'date_deadline': due.date() if due else fields.Date.context_today(self), 'user_id': user.id}
        completed = (p.get('hs_task_status') or '').upper() == 'COMPLETED'
        if record:
            changed = self._write_changed(record, vals)
            if completed and record.active:
                record.action_feedback(feedback=self.env._('Completed in HubSpot'))
                changed = True
            return record, self._result(changed)
        target = self._engagement_target(account, data)
        activity = self.env['mail.activity'].create({
            **vals, 'res_model_id': self.env['ir.model']._get_id(target._name), 'res_id': target.id,
            'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id})
        if completed:
            activity.action_feedback(feedback=self.env._('Completed in HubSpot'))
        return activity.with_context(active_test=False).exists(), 'created'

    def _export_tasks(self, account, activity):
        due = datetime.combine(activity.date_deadline, time(9, 0)) if activity.date_deadline else fields.Datetime.now()
        return {'hs_task_subject': activity.summary or activity.activity_type_id.name or '',
                'hs_task_body': str(activity.note or ''),
                'hs_task_status': 'NOT_STARTED' if activity.active else 'COMPLETED',
                'hs_timestamp': to_hubspot_datetime(due),
                'hubspot_owner_id': self._owner(account, activity.user_id)}

    def _import_meetings(self, account, data, record):
        p = data['properties']
        start = from_hubspot_datetime(p.get('hs_meeting_start_time') or p.get('hs_timestamp')) or fields.Datetime.now()
        stop = from_hubspot_datetime(p.get('hs_meeting_end_time')) or start + timedelta(hours=1)
        user = self._user(account, p.get('hubspot_owner_id')) or account.default_user_id or self.env.user
        attendees = self.env['res.partner']
        for contact_id in (data.get('associations') or {}).get('contacts') or []:
            link = self._link_model()._get(account, 'contacts', hubspot_id=contact_id)
            if link and link._record():
                attendees |= link._record()
        vals = {'name': p.get('hs_meeting_title') or self.env._('HubSpot meeting'),
                'description': Markup(html_sanitize(p.get('hs_meeting_body') or '')),
                'start': start, 'stop': max(stop, start), 'location': p.get('hs_meeting_location') or False,
                'user_id': user.id}
        Event = self.env['calendar.event'].with_context(no_mail_to_attendees=True, mail_create_nosubscribe=True)
        if record:
            changed = self._write_changed(record.with_context(no_mail_to_attendees=True), vals)
            missing = attendees - record.partner_ids
            if missing:
                record.with_context(no_mail_to_attendees=True).partner_ids = [(4, pid) for pid in missing.ids]
                changed = True
            return record, self._result(changed)
        try:
            target = self._engagement_target(account, data)
        except HubspotSkip:
            if not attendees:
                raise
            target = attendees[:1]
        vals.update(partner_ids=[(6, 0, (attendees | user.partner_id).ids)],
                    res_model_id=self.env['ir.model']._get_id(target._name), res_id=target.id)
        return Event.create(vals), 'created'

    def _export_meetings(self, account, event):
        return {'hs_meeting_title': event.name or '', 'hs_meeting_body': html2plaintext(event.description or ''),
                'hs_meeting_start_time': to_hubspot_datetime(event.start),
                'hs_meeting_end_time': to_hubspot_datetime(event.stop),
                'hs_meeting_location': event.location or '', 'hs_timestamp': to_hubspot_datetime(event.start),
                'hubspot_owner_id': self._owner(account, event.user_id)}

    def _associate_engagement(self, account, object_type, hubspot_id, link, targets):
        client = account._client()
        done = set((link.extra or {}).get('associated', []))
        for target_type, target_id in targets:
            key = f'{target_type}:{target_id}'
            if target_id and key not in done:
                client.associate(object_type, hubspot_id, target_type, target_id)
                done.add(key)
        link.extra = dict(link.extra or {}, associated=sorted(done))

    def _after_export_notes(self, account, message, hubspot_id, link):
        target = self._engagement_target_link(account, message)
        self._associate_engagement(account, 'notes', hubspot_id, link, [(target.object_type, target.hubspot_id)])

    def _after_export_emails(self, account, message, hubspot_id, link):
        target = self._engagement_target_link(account, message)
        self._associate_engagement(account, 'emails', hubspot_id, link, [(target.object_type, target.hubspot_id)])

    def _after_export_tasks(self, account, activity, hubspot_id, link):
        target = self._engagement_target_link(account, activity)
        self._associate_engagement(account, 'tasks', hubspot_id, link, [(target.object_type, target.hubspot_id)])

    def _after_export_meetings(self, account, event, hubspot_id, link):
        targets = []
        for partner in event.partner_ids:
            partner_link = self._partner_link(account, partner)
            if partner_link:
                targets.append((partner_link.object_type, partner_link.hubspot_id))
        if event.res_model == 'crm.lead' and event.res_id:
            deal = self._link_model()._get(account, 'deals', record=self.env['crm.lead'].browse(event.res_id))
            if deal:
                targets.append(('deals', deal.hubspot_id))
        self._associate_engagement(account, 'meetings', hubspot_id, link, targets)
