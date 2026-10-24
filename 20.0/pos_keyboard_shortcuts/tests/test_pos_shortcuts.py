from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.point_of_sale.tests.test_frontend import TestPointOfSaleHttpCommon

from ..models.pos_shortcut import DEFAULTS, normalize_key


@tagged('post_install', '-at_install')
class TestPosShortcuts(TestPointOfSaleHttpCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.main_pos_config
        cls.config.action_load_default_shortcuts()

    def test_normalize_key(self):
        self.assertEqual(normalize_key('Shift + P'), 'shift+p')
        self.assertEqual(normalize_key('Control+Del'), 'ctrl+delete')
        self.assertEqual(normalize_key('alt+ctrl+N'), 'ctrl+alt+n')
        self.assertEqual(normalize_key('F10'), 'f10')
        self.assertEqual(normalize_key('shift++'), 'shift++')
        for bad in ('', 'hyper+p', 'shift+shift+p', 'shift+banana'):
            with self.assertRaises(ValueError):
                normalize_key(bad)

    def test_defaults(self):
        shortcuts = self.config.shortcut_ids
        self.assertTrue(self.config.shortcut_enabled)
        self.assertGreaterEqual(len(shortcuts), len(DEFAULTS))
        cash = shortcuts.filtered(lambda s: s.action == 'payment_method' and s.key == 'c')
        self.assertTrue(cash.payment_method_id.type == 'cash')
        bank = shortcuts.filtered(lambda s: s.action == 'payment_method' and s.key == 'b')
        self.assertEqual(bank.payment_method_id.type, 'bank', "b is never the customer account")
        count = len(shortcuts)
        self.config.action_load_default_shortcuts()
        self.assertEqual(len(self.config.shortcut_ids), count, "loading defaults twice adds nothing")

    def test_bank_key_skips_customer_account(self):
        # a "Customer Account" (pay later) method listed first must not get the bank key
        account = self.env['pos.payment.method'].create({'name': 'Customer Account', 'type': 'pay_later', 'sequence': -1})
        self.assertEqual(account.type, 'pay_later')
        config = self.config
        config.payment_method_ids = [(4, account.id)]
        self.env.invalidate_all()
        self.assertEqual(config.payment_method_ids[:1], account)
        config.shortcut_ids.filtered(lambda s: s.key == 'b').unlink()
        config.action_load_default_shortcuts()
        bank = config.shortcut_ids.filtered(lambda s: s.key == 'b')
        self.assertEqual(bank.payment_method_id.type, 'bank')

    def test_constraints(self):
        Shortcut = self.env['pos.shortcut']
        with self.assertRaises(Exception), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                Shortcut.create({'config_id': self.config.id, 'screen': 'product', 'action': 'pay', 'key': 'Shift+P'})
        with self.assertRaises(ValidationError):
            Shortcut.create({'config_id': self.config.id, 'screen': 'payment', 'action': 'payment_method', 'key': 'x'})
        with self.assertRaises(ValidationError):
            Shortcut.create({'config_id': self.config.id, 'screen': 'product', 'action': 'pay', 'key': 'super+x'})
        # same key on another screen is fine
        shortcut = Shortcut.create({'config_id': self.config.id, 'screen': 'payment', 'action': 'validate', 'key': 'Shift + P'})
        self.assertEqual(shortcut.key, 'shift+p')

    def test_loaded_in_pos_data(self):
        data = self.env['pos.config']._load_pos_data_read(self.config, self.config)[0]
        keys = {(s['screen'], s['key']) for s in data['_pos_shortcuts']}
        self.assertIn(('product', 'shift+p'), keys)
        labels = {s['key']: s['label'] for s in data['_pos_shortcuts'] if s['screen'] == 'payment'}
        self.assertEqual(labels['c'], self.config.payment_method_ids.filtered(lambda m: m.type == 'cash')[:1].name)
        self.config.shortcut_enabled = False
        data = self.env['pos.config']._load_pos_data_read(self.config, self.config)[0]
        self.assertEqual(data['_pos_shortcuts'], [])

    def test_settings_button(self):
        config = self.config.copy({'name': 'Second shop'})
        settings = self.env['res.config.settings'].create({'pos_config_id': config.id, 'pos_shortcut_enabled': True})
        action = settings.action_pos_shortcuts()
        self.assertEqual(action['domain'], [('config_id', '=', config.id)])
        self.assertTrue(config.shortcut_ids)

    def test_pos_tour(self):
        self.start_pos_tour('pos_keyboard_shortcuts_tour')
        order = self.env['pos.order'].search([('config_id', '=', self.config.id)], order='id desc', limit=1)
        self.assertEqual(len(order.lines), 1)
        self.assertEqual(order.payment_ids.payment_method_id, self.config.payment_method_ids.filtered(lambda m: m.type == 'cash')[:1])
        self.assertIn(order.state, ('paid', 'done', 'invoiced'))
