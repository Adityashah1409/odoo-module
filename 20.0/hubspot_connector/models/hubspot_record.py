import hashlib
import json

from odoo import api, fields, models

from .hubspot_account import OBJECT_TYPES


class HubspotRecord(models.Model):
    """Link between an Odoo record and a HubSpot object, with the fingerprint of the last synchronized values."""
    _name = 'hubspot.record'
    _description = 'HubSpot link'
    _order = 'id desc'
    _rec_name = 'hubspot_id'

    account_id = fields.Many2one('hubspot.account', required=True, ondelete='cascade', index=True)
    object_type = fields.Selection(OBJECT_TYPES, required=True, index=True)
    hubspot_id = fields.Char('HubSpot ID', required=True, index=True)
    res_model = fields.Char(required=True, index=True)
    res_id = fields.Many2oneReference('Record', model_field='res_model', required=True, index=True)
    record_name = fields.Char(compute='_compute_record_name')
    fingerprint = fields.Char(help='Hash of the properties last received from or sent to HubSpot.')
    last_sync = fields.Datetime()
    extra = fields.Json(help='Technical data, e.g. the line items created for a quote.')
    hubspot_url = fields.Char(compute='_compute_hubspot_url')

    _hubspot_uniq = models.Constraint('UNIQUE(account_id, object_type, hubspot_id)',
                                      'This HubSpot object is already linked.')
    _record_uniq = models.Constraint('UNIQUE(account_id, object_type, res_model, res_id)',
                                     'This record is already linked to HubSpot.')

    def _compute_record_name(self):
        for link in self:
            record = self.env[link.res_model].browse(link.res_id).exists() if link.res_model in self.env else None
            link.record_name = record.display_name if record else f'{link.res_model},{link.res_id} (deleted)'

    def _compute_hubspot_url(self):
        for link in self:
            link.hubspot_url = link.account_id._record_url(link.object_type, link.hubspot_id)

    @api.model
    def _fingerprint(self, properties):
        canonical = json.dumps({k: _normalize(v) for k, v in (properties or {}).items()}, sort_keys=True)
        return hashlib.sha1(canonical.encode()).hexdigest()

    @api.model
    def _get(self, account, object_type, hubspot_id=None, record=None):
        domain = [('account_id', '=', account.id), ('object_type', '=', object_type)]
        if hubspot_id is not None:
            domain.append(('hubspot_id', '=', str(hubspot_id)))
        if record is not None:
            domain += [('res_model', '=', record._name), ('res_id', '=', record.id)]
        return self.search(domain, limit=1)

    def _record(self):
        self.ensure_one()
        return self.env[self.res_model].with_context(active_test=False).browse(self.res_id).exists()

    @api.model
    def _set(self, account, object_type, hubspot_id, record, properties):
        link = self._get(account, object_type, hubspot_id=hubspot_id) or self._get(account, object_type, record=record)
        vals = {'account_id': account.id, 'object_type': object_type, 'hubspot_id': str(hubspot_id),
                'res_model': record._name, 'res_id': record.id, 'fingerprint': self._fingerprint(properties),
                'last_sync': fields.Datetime.now()}
        if link:
            link.write(vals)
            return link
        return self.create(vals)

    def action_open_record(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id,
                'views': [(False, 'form')], 'target': 'current'}

    def action_open_hubspot(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.hubspot_url, 'target': 'new'} if self.hubspot_url else False


def _normalize(value):
    """Same value on both sides -> same text (HubSpot returns everything as strings)."""
    if value in (None, False, ''):
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return ('%.6f' % value).rstrip('0').rstrip('.')
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text
    if text.lower() in ('nan', 'inf', '-inf', 'infinity'):
        return text
    return ('%.6f' % number).rstrip('0').rstrip('.')
