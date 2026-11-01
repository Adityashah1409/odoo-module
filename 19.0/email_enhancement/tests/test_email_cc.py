from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user

from odoo.addons.base.tests.common import MockSmtplibCase


class TestEmailCc(TransactionCase, MockSmtplibCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({'mail_default_cc': False, 'mail_default_bcc': 'archive@example.com',
                           'mail_default_reply_to': False, 'email': 'info@example.com'})
        cls.user = new_test_user(cls.env, 'cc_user', groups='base.group_user,base.group_partner_manager',
                                 email='sam@example.com', name='Sam Sender')
        cls.customer = cls.env['res.partner'].create({'name': 'Delta Logistics', 'email': 'buyer@delta.example.com'})
        cls.Rule = cls.env['mail.cc.rule']
        cls.partner_model = cls.env['ir.model']._get('res.partner')

    def _composer(self, user=None, **ctx):
        context = dict({'default_model': 'res.partner', 'default_res_ids': self.customer.ids,
                        'default_composition_mode': 'comment'}, **ctx)
        return self.env['mail.compose.message'].with_user(user or self.user).with_context(context).create({
            'body': '<p>Hello, the offer is attached.</p>', 'subject': 'Offer',
            'partner_ids': [(6, 0, self.customer.ids)]})

    def test_defaults_from_company_and_rules(self):
        self.Rule.create({'name': 'Contacts', 'model_ids': [(6, 0, self.partner_model.ids)],
                          'email_cc': 'assistant@example.com', 'reply_to': 'sales@example.com'})
        self.Rule.create({'name': 'Sam', 'user_ids': [(6, 0, self.user.ids)],
                          'email_cc': 'Assistant@example.com, boss@example.com', 'email_bcc': 'boss@example.com'})
        self.Rule.create({'name': 'Admins only', 'group_ids': [(6, 0, self.env.ref('base.group_system').ids)],
                          'email_cc': 'it@example.com'})
        self.Rule.create({'name': 'Other model', 'model_ids': [(6, 0, self.env['ir.model']._get('res.users').ids)],
                          'email_cc': 'hr@example.com'})
        defaults = self.Rule.with_user(self.user)._get_defaults('res.partner', self.user)
        self.assertEqual(defaults['cc'], ['assistant@example.com', 'boss@example.com'], 'union without duplicates')
        self.assertEqual(defaults['bcc'], ['archive@example.com'], 'Bcc already in Cc is dropped')
        self.assertEqual(defaults['reply_to'], 'sales@example.com')
        composer = self._composer()
        self.assertEqual(composer.extra_email_cc, 'assistant@example.com, boss@example.com')
        self.assertEqual(composer.extra_email_bcc, 'archive@example.com')
        self.assertEqual(composer.reply_to, 'sales@example.com')
        self.assertIn('it@example.com', self.Rule._get_defaults('res.partner', self.env.ref('base.user_admin'))['cc'])

    def test_send_comment_with_cc_bcc(self):
        composer = self._composer()
        composer.write({'extra_email_cc': 'assistant@example.com', 'extra_email_bcc': 'boss@example.com'})
        composer._action_send_mail()
        message = self.customer.message_ids.filtered(lambda m: m.subject == 'Offer')
        self.assertEqual(message.extra_email_cc, 'assistant@example.com')
        mails = self.env['mail.mail'].sudo().search([('mail_message_id', '=', message.id)])
        self.assertTrue(mails)
        with_cc = mails.filtered('email_cc')
        self.assertEqual(len(with_cc), 1, 'Cc on one e-mail only')
        self.assertEqual(with_cc.email_cc, 'assistant@example.com')
        self.assertEqual(with_cc.email_bcc, 'boss@example.com')
        log = self.customer.message_ids.filtered(lambda m: 'Bcc: boss@example.com' in (m.body or ''))
        self.assertTrue(log, 'the chatter shows who was in copy')

        # Bcc reaches the SMTP envelope, never the headers
        with self.mock_smtplib_connection():
            mails.send()
        self.assertTrue(self.emails, 'the e-mails were handed to the SMTP server')
        recipients = [address for email in self.emails for address in email['smtp_to_list']]
        self.assertEqual(recipients.count('boss@example.com'), 1, 'one hidden copy only')
        self.assertIn('assistant@example.com', recipients)
        self.assertIn('buyer@delta.example.com', recipients)
        self.assertTrue(any(email['msg_cc'] == 'assistant@example.com' for email in self.emails))
        for email in self.emails:
            self.assertNotIn('boss@example.com', email['message'], 'no Bcc in the headers or the body')

    def test_log_note_has_no_cc(self):
        composer = self._composer(default_subtype_xmlid='mail.mt_note')
        self.assertFalse(composer.extra_email_bcc)

    def test_mass_mail(self):
        other = self.env['res.partner'].create({'name': 'Kessler GmbH', 'email': 'einkauf@kessler.example.com'})
        composer = self.env['mail.compose.message'].with_context(
            default_model='res.partner', default_res_ids=(self.customer | other).ids,
            default_composition_mode='mass_mail').create({
                'subject': 'News', 'body': '<p>News</p>', 'extra_email_cc': 'marketing@example.com'})
        composer._action_send_mail()
        mails = self.env['mail.mail'].sudo().search([('subject', '=', 'News')])
        self.assertEqual(len(mails), 2)
        self.assertEqual(set(mails.mapped('email_cc')), {'marketing@example.com'})
        self.assertEqual(set(mails.mapped('email_bcc')), {'archive@example.com'})

    def test_validation(self):
        with self.assertRaises(ValidationError):
            self.Rule.create({'name': 'Bad', 'email_cc': 'not an e-mail'})
        with self.assertRaises(ValidationError):
            self.Rule.create({'name': 'Empty'})
        with self.assertRaises(ValidationError):
            self.company.write({'mail_default_cc': 'nope'})
            self.company.flush_recordset()
        composer = self._composer()
        composer.extra_email_cc = 'wrong address'
        with self.assertRaises(ValidationError):
            composer._action_send_mail()
