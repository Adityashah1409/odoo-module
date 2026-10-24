from odoo import api, fields, models


class PosConfig(models.Model):
    _inherit = 'pos.config'

    auto_discount_enabled = fields.Boolean('Automatic discounts')
    auto_discount_badge = fields.Boolean(
        'Show discount badges', default=True, help='Show the discount on product cards (rules without minimum quantity).')

    @api.model
    def _load_pos_data_read(self, records, config):
        result = super()._load_pos_data_read(records, config)
        if result:
            rules = self.env['pos.auto.discount']
            if config.auto_discount_enabled:
                rules = rules._rules_for_config(config)
            result[0]['_pos_auto_discounts'] = rules._pos_data()
        return result

    def action_open_auto_discounts(self):
        action = self.env['ir.actions.act_window']._for_xml_id('pos_product_auto_discount.action_pos_auto_discount')
        action['context'] = {'default_config_ids': [(6, 0, self.ids)]}
        return action
