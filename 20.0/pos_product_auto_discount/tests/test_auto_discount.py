from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon


@tagged('post_install', '-at_install')
class TestPosAutoDiscount(TestPointOfSaleHttpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.main_pos_config
        cls.config.auto_discount_enabled = True
        Rule = cls.env['pos.auto.discount']
        organizer = cls.env['product.template'].search([('name', '=', 'Desk Organizer')], limit=1)
        tray = cls.env['product.template'].search([('name', '=', 'Letter Tray')], limit=1)
        board = cls.env['product.template'].search([('name', '=', 'Magnetic Board')], limit=1)
        today = fields.Date.context_today(Rule)
        cls.promo = Rule.create({'name': 'Organizer promo', 'discount': 10, 'product_tmpl_ids': organizer.ids})
        cls.bulk = Rule.create({'name': 'Organizer bulk', 'discount': 25, 'min_qty': 3, 'product_tmpl_ids': organizer.ids})
        cls.expired = Rule.create({'name': 'Old tray sale', 'discount': 50, 'product_tmpl_ids': tray.ids,
                                   'date_from': today - timedelta(days=10), 'date_to': today - timedelta(days=1)})
        cls.board_rule = Rule.create({'name': 'Board week', 'discount': 20, 'product_tmpl_ids': board.ids})
        cls.other_shop = cls.config.copy({'name': 'Other shop'})
        cls.other_rule = Rule.create({'name': 'Other shop only', 'discount': 40, 'applies_on': 'all',
                                      'config_ids': cls.other_shop.ids})

    def _pos_rules(self, config):
        return self.env['pos.config']._load_pos_data_read(config, config)[0]['_pos_auto_discounts']

    def test_rules_sent_to_register(self):
        names = {r['name'] for r in self._pos_rules(self.config)}
        self.assertEqual(names, {'Organizer promo', 'Organizer bulk', 'Board week'})
        bulk = next(r for r in self._pos_rules(self.config) if r['name'] == 'Organizer bulk')
        self.assertEqual(bulk['min_qty'], 3)
        self.assertEqual(bulk['product_tmpl_ids'], self.bulk.product_tmpl_ids.ids)
        self.assertIn('Other shop only', {r['name'] for r in self._pos_rules(self.other_shop)})
        self.config.auto_discount_enabled = False
        self.assertEqual(self._pos_rules(self.config), [])

    def test_status(self):
        self.assertEqual(self.promo.status, 'running')
        self.assertEqual(self.expired.status, 'expired')
        self.promo.date_from = fields.Date.context_today(self.promo) + timedelta(days=2)
        self.assertEqual(self.promo.status, 'scheduled')

    def test_constraints(self):
        Rule = self.env['pos.auto.discount']
        for bad in ({'discount': 0}, {'discount': 120}, {'min_qty': -1}):
            with self.assertRaises(Exception), mute_logger('odoo.sql_db'), self.env.cr.savepoint():
                Rule.create(dict({'name': 'bad', 'discount': 10, 'applies_on': 'all'}, **bad))
        with self.assertRaises(ValidationError):
            Rule.create({'name': 'no product', 'discount': 10, 'applies_on': 'products'})
        with self.assertRaises(ValidationError):
            Rule.create({'name': 'no category', 'discount': 10, 'applies_on': 'categories'})
        with self.assertRaises(ValidationError):
            Rule.create({'name': 'dates', 'discount': 10, 'applies_on': 'all',
                         'date_from': '2030-02-01', 'date_to': '2030-01-01'})
        with self.assertRaises(ValidationError):
            Rule.create({'name': 'hours', 'discount': 10, 'applies_on': 'all', 'hour_from': 25})

    def test_settings_button(self):
        settings = self.env['res.config.settings'].create({'pos_config_id': self.config.id})
        action = settings.action_pos_auto_discounts()
        self.assertEqual(action['res_model'], 'pos.auto.discount')
        self.assertEqual(action['context']['default_config_ids'], [(6, 0, self.config.ids)])

    def test_pos_tour(self):
        self.start_pos_tour('pos_auto_discount_tour')
        order = self.env['pos.order'].search([('config_id', '=', self.config.id)], order='id desc', limit=1)
        lines = {line.product_id.name: line for line in order.lines}
        organizer, tray, board = lines['Desk Organizer'], lines['Letter Tray'], lines['Magnetic Board']
        self.assertEqual((organizer.qty, organizer.discount, organizer.auto_discount_id), (3, 25, self.bulk))
        self.assertAlmostEqual(organizer.auto_discount_amount, organizer.price_subtotal_incl / 3, places=2)
        self.assertEqual((tray.discount, tray.auto_discount_id.id), (0, False))
        self.assertEqual((board.qty, board.discount, board.auto_discount_id.id), (2, 5, False))
        self.assertEqual(self.bulk.line_count, 1)
        self.assertAlmostEqual(self.bulk.discount_amount, organizer.auto_discount_amount, places=2)
        action = self.bulk.action_view_lines()
        self.assertEqual(self.env['pos.order.line'].search(action['domain']), organizer)
