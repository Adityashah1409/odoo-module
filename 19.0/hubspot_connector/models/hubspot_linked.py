from odoo import fields, models


class HubspotLinkedMixin(models.AbstractModel):
    """HubSpot id / link shown on synchronized Odoo records."""
    _name = 'hubspot.linked.mixin'
    _description = 'HubSpot linked record'

    hubspot_id = fields.Char('HubSpot ID', compute='_compute_hubspot_link', search='_search_hubspot_id',
                             groups='hubspot_connector.group_hubspot_manager')
    hubspot_url = fields.Char('HubSpot link', compute='_compute_hubspot_link',
                              groups='hubspot_connector.group_hubspot_manager')

    def _compute_hubspot_link(self):
        links = self.env['hubspot.record'].sudo().search([('res_model', '=', self._name), ('res_id', 'in', self.ids)])
        per_record = {}
        for link in links:
            per_record.setdefault(link.res_id, link)
        for record in self:
            link = per_record.get(record.id)
            record.hubspot_id = link.hubspot_id if link else False
            record.hubspot_url = link.hubspot_url if link else False

    def _search_hubspot_id(self, operator, value):
        links = self.env['hubspot.record'].sudo().search([('res_model', '=', self._name), ('hubspot_id', operator, value)])
        return [('id', 'in', links.mapped('res_id'))]

    def action_open_hubspot(self):
        self.ensure_one()
        if not self.hubspot_url:
            return False
        return {'type': 'ir.actions.act_url', 'url': self.hubspot_url, 'target': 'new'}


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'hubspot.linked.mixin']


class CrmLead(models.Model):
    _name = 'crm.lead'
    _inherit = ['crm.lead', 'hubspot.linked.mixin']


class ProductTemplate(models.Model):
    _name = 'product.template'
    _inherit = ['product.template', 'hubspot.linked.mixin']


class SaleOrder(models.Model):
    _name = 'sale.order'
    _inherit = ['sale.order', 'hubspot.linked.mixin']


class AccountMove(models.Model):
    _name = 'account.move'
    _inherit = ['account.move', 'hubspot.linked.mixin']
