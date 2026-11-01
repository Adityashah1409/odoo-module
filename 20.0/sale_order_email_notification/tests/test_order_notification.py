from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user


class TestOrderNotification(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.manager = new_test_user(cls.env, 'so_manager', groups='sales_team.group_sale_manager',
                                    email='manager@example.com', name='Maria Manager')
        cls.seller = new_test_user(cls.env, 'so_seller', groups='sales_team.group_sale_salesman',
                                   email='seller@example.com', name='Sam Seller')
        cls.leader = new_test_user(cls.env, 'so_leader', groups='sales_team.group_sale_salesman',
                                   email='leader@example.com', name='Lea Leader')
        cls.team = cls.env['crm.team'].create({'name': 'Export', 'user_id': cls.leader.id})
        cls.other_team = cls.env['crm.team'].create({'name': 'Retail'})
        cls.customer = cls.env['res.partner'].create({'name': 'Delta Logistics', 'email': 'buyer@delta.example.com'})
        cls.product = cls.env['product.product'].create({'name': 'Office desk', 'list_price': 500})
        cls.Rule = cls.env['sale.order.notification.rule']
        cls.Rule.search([]).active = False

    def _order(self, qty=2, team=None, user=None):
        return self.env['sale.order'].create({
            'partner_id': self.customer.id, 'user_id': (user or self.seller).id, 'team_id': (team or self.team).id,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': qty, 'price_unit': 500})],
        })

    def _mails(self, order):
        return self.env['mail.mail'].search([('subject', 'ilike', order.name)])

    def test_confirm_rule_recipients(self):
        rule = self.Rule.create({'name': 'Confirmed orders', 'trigger': 'confirm', 'user_ids': self.manager.ids,
                                 'email_list': 'orders@example.com, Seller@example.com', 'notify_salesperson': True,
                                 'notify_team_leader': True})
        order = self._order()
        self.assertFalse(self._mails(order), 'nothing for a new quotation')
        order.action_confirm()
        mail = self._mails(order).filtered(lambda m: 'Order confirmed' in m.subject)
        self.assertEqual(len(mail), 1)
        self.assertEqual(mail.recipient_ids, (self.manager | self.seller | self.leader).partner_id)
        self.assertEqual(mail.email_to, 'orders@example.com', 'the salesperson is not written twice')
        self.assertNotIn(self.customer, mail.recipient_ids)
        self.assertIn('Office desk', mail.body_html)
        self.assertIn(order.name, mail.subject)
        self.assertEqual(rule.sent_count, 4)
        self.assertIn('Notification "Confirmed orders" sent to', order.message_ids[0].body)
        self.assertFalse(mail.model, 'internal e-mail not in the chatter of the order')
        self.assertFalse(order.message_ids.filtered(lambda m: 'Order confirmed' in (m.subject or '')))

    def test_create_and_cancel_triggers(self):
        self.Rule.create({'name': 'New quotations', 'trigger': 'create', 'notify_salesperson': True})
        self.Rule.create({'name': 'Cancelled', 'trigger': 'cancel', 'user_ids': self.manager.ids})
        order = self._order()
        mails = self._mails(order)
        self.assertEqual(len(mails), 1)
        self.assertIn('New quotation', mails.subject)
        self.assertEqual(mails.recipient_ids, self.seller.partner_id)
        order._action_cancel()
        cancel_mail = self._mails(order) - mails
        self.assertIn('Order cancelled', cancel_mail.subject)
        self.assertEqual(cancel_mail.recipient_ids, self.manager.partner_id)
        order.with_context(skip_order_notification=True).copy()

    def test_filters(self):
        self.Rule.create({'name': 'Big export orders', 'trigger': 'confirm', 'user_ids': self.manager.ids,
                          'team_ids': [(6, 0, self.team.ids)], 'min_amount': 2000})
        small = self._order(qty=2)          # 1000
        big_other_team = self._order(qty=10, team=self.other_team)
        big = self._order(qty=10)
        (small | big_other_team | big).action_confirm()
        self.assertFalse(self._mails(small))
        self.assertFalse(self._mails(big_other_team))
        self.assertTrue(self._mails(big))
        # channel: without eCommerce every order is a back-office order
        self.Rule.create({'name': 'Shop', 'trigger': 'confirm', 'channel': 'website', 'user_ids': self.leader.ids})
        order = self._order()
        order.action_confirm()
        self.assertFalse(self._mails(order).filtered(lambda m: self.leader.partner_id in m.recipient_ids))
        self.assertEqual(order._order_notification_channel(), 'backend')

    def test_customer_and_pdf(self):
        self.Rule.create({'name': 'Customer copy', 'trigger': 'confirm', 'notify_customer': True,
                          'email_list': 'orders@example.com', 'attach_pdf': True})
        order = self._order()
        order.with_context(skip_order_notification=False).action_confirm()
        mails = self._mails(order)
        to_customer = mails.filtered(lambda m: self.customer in m.recipient_ids)
        internal = mails.filtered(lambda m: m.email_to == 'orders@example.com')
        self.assertTrue(to_customer)
        self.assertTrue(internal)
        self.assertTrue(internal.attachment_ids)
        self.assertTrue(all(a.name.endswith('.pdf') for a in internal.attachment_ids))

    def test_inactive_rule_and_test_button(self):
        rule = self.Rule.create({'name': 'Off', 'trigger': 'confirm', 'user_ids': self.manager.ids,
                                 'active': False})
        order = self._order()
        order.action_confirm()
        self.assertFalse(self._mails(order))
        action = rule.with_user(self.manager).action_test()
        self.assertEqual(action['params']['type'], 'success')
        self.assertTrue(self._mails(order))

    def test_email_list_validation(self):
        with self.assertRaises(ValidationError):
            self.Rule.create({'name': 'Bad', 'trigger': 'confirm', 'email_list': 'not an address'})

    def test_access(self):
        rule = self.Rule.create({'name': 'Rule', 'trigger': 'confirm'})
        self.assertTrue(rule.with_user(self.seller).name)
        with self.assertRaises(Exception):
            rule.with_user(self.seller).write({'name': 'x'})
        # a salesperson confirming an order still triggers the rule (sudo inside)
        rule.write({'user_ids': self.manager.ids})
        order = self._order().with_user(self.seller)
        order.action_confirm()
        self.assertTrue(self._mails(order))
