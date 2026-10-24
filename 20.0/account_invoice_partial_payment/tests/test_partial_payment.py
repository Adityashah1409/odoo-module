from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestPartialPayment(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank = cls.company_data['default_journal_bank']
        cls.inv_old = cls.init_invoice('out_invoice', partner=cls.partner_a, invoice_date='2026-08-01', amounts=[1000], taxes=[], post=True)
        cls.inv_new = cls.init_invoice('out_invoice', partner=cls.partner_a, invoice_date='2026-09-01', amounts=[500], taxes=[], post=True)
        cls.bill = cls.init_invoice('in_invoice', partner=cls.partner_b, invoice_date='2026-09-01', amounts=[800], taxes=[], post=True)
        cls.Batch = cls.env['account.partial.payment']

    def _batch(self, amount, allocations, payment_type='inbound', partner=None):
        return self.Batch.create({
            'payment_type': payment_type,
            'partner_id': (partner or self.partner_a).id,
            'journal_id': self.bank.id,
            'amount': amount,
            'date': '2026-10-20',
            'memo': 'Cheque 1042',
            'line_ids': [(0, 0, {'move_id': move.id, 'amount': value}) for move, value in allocations],
        })

    def test_customer_receipt_split_with_rest(self):
        batch = self._batch(1200, [(self.inv_old, 700), (self.inv_new, 400)])
        self.assertEqual((batch.allocated_amount, batch.unallocated_amount), (1100, 100))
        batch.action_post()
        self.assertEqual(batch.state, 'posted')
        self.assertTrue(batch.name.startswith('PPAY/'))
        self.assertEqual(len(batch.payment_ids), 3)
        self.assertEqual(sum(batch.payment_ids.mapped('amount')), 1200)
        self.assertTrue(all(p.state in ('in_process', 'paid') for p in batch.payment_ids))
        self.assertAlmostEqual(self.inv_old.amount_residual, 300)
        self.assertAlmostEqual(self.inv_new.amount_residual, 100)
        self.assertEqual(self.inv_old.payment_state, 'partial')
        self.assertEqual(batch.line_ids.mapped('amount_residual'), [1000, 500], 'amount due before the batch')
        self.assertEqual(batch.line_ids.mapped('remaining'), [300, 100])
        # the rest is an outstanding credit of the customer
        next_batch = self.Batch.new({'payment_type': 'inbound', 'partner_id': self.partner_a.id, 'journal_id': self.bank.id})
        self.assertAlmostEqual(next_batch.partner_outstanding, 100)
        self.assertTrue(self.inv_old.invoice_has_outstanding)
        self.assertEqual((batch.payment_count, batch.invoice_count), (3, 2))

    def test_full_payment_marks_invoice_paid(self):
        batch = self._batch(500, [(self.inv_new, 500)])
        batch.action_post()
        self.assertIn(self.inv_new.payment_state, ('in_payment', 'paid'))
        self.assertEqual(len(batch.payment_ids), 1)
        self.assertFalse(batch.unallocated_amount)

    def test_vendor_bills(self):
        batch = self._batch(300, [(self.bill, 300)], payment_type='outbound', partner=self.partner_b)
        batch.action_post()
        self.assertAlmostEqual(self.bill.amount_residual, 500)
        self.assertEqual(batch.payment_ids.payment_type, 'outbound')

    def test_checks(self):
        with self.assertRaises(ValidationError):
            self._batch(1200, [(self.inv_old, 1200)]).action_post()  # more than due
        with self.assertRaises(ValidationError):
            self._batch(500, [(self.inv_old, 400), (self.inv_new, 200)]).action_post()  # more than received
        with self.assertRaises(ValidationError):
            self._batch(0, []).action_post()
        with self.assertRaises(ValidationError):
            self._batch(100, [(self.bill, 100)]).action_post()  # bill of another partner / type
        posted = self._batch(100, [(self.inv_new, 100)])
        posted.action_post()
        with self.assertRaises(UserError):
            posted.action_post()
        with self.assertRaises(UserError):
            posted.unlink()

    def test_load_and_auto_allocate(self):
        batch = self._batch(1100, [])
        batch.action_load_invoices()
        self.assertEqual(batch.line_ids.move_id, self.inv_old | self.inv_new)
        self.assertFalse(any(batch.line_ids.mapped('amount')))
        batch.action_auto_allocate()
        amounts = {line.move_id: line.amount for line in batch.line_ids}
        self.assertEqual((amounts[self.inv_old], amounts[self.inv_new]), (1000, 100), 'oldest due first')
        batch.action_load_invoices()
        self.assertEqual(len(batch.line_ids), 2, 'no duplicates')

    def test_cancel_reopens_invoices(self):
        batch = self._batch(800, [(self.inv_old, 600)])
        batch.action_post()
        self.assertAlmostEqual(self.inv_old.amount_residual, 400)
        batch.action_cancel()
        self.assertEqual(batch.state, 'cancel')
        self.assertAlmostEqual(self.inv_old.amount_residual, 1000)
        self.assertTrue(all(p.state == 'canceled' for p in batch.payment_ids))
        batch.action_draft()
        self.assertEqual((batch.state, len(batch.payment_ids)), ('draft', 0))

    def test_button_on_invoice(self):
        action = self.inv_new.action_partial_payment()
        with Form(self.Batch.with_context(action['context'])) as form:
            form.amount = 200
            with form.line_ids.edit(0) as line:
                line.amount = 200
        batch = form.record
        self.assertEqual((batch.partner_id, batch.payment_type), (self.partner_a, 'inbound'))
        self.assertEqual(batch.line_ids.move_id, self.inv_new)
        batch.action_post()
        self.assertAlmostEqual(self.inv_new.amount_residual, 300)
