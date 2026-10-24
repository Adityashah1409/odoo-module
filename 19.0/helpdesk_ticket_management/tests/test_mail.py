from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import SupportCommon

RAW_EMAIL = """Return-Path: <{email_from}>
To: {to}
From: {email_from}
Subject: {subject}
Message-ID: {msg_id}
{extra}MIME-Version: 1.0
Content-Type: text/plain; charset=utf-8

{body}
"""


@tagged('post_install', '-at_install')
class TestSupportMail(SupportCommon):

    def _process(self, subject, email_from, body, msg_id, extra='', to='level1@example.com'):
        raw = RAW_EMAIL.format(subject=subject, email_from=email_from, body=body, msg_id=msg_id, extra=extra, to=to)
        with mute_logger('odoo.addons.mail.models.mail_thread'):
            return self.env['mail.thread'].message_process('support.ticket', raw, custom_values={'team_id': self.team.id})

    def test_alias(self):
        self.assertEqual(self.team.alias_id.alias_model_id.model, 'support.ticket')
        self.assertIn(f"'team_id': {self.team.id}", self.team.alias_defaults)

    def test_gateway_new_and_reply(self):
        ticket_id = self._process('My screen is black', 'New Person <new.person@example.com>',
                                  'Since this morning.', '<first-1@example.com>')
        ticket = self.env['support.ticket'].browse(ticket_id)
        self.assertEqual(ticket.name, 'My screen is black')
        self.assertEqual(ticket.channel, 'email')
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.partner_id.email, 'new.person@example.com', 'the sender becomes a contact')
        self.assertIn('Since this morning', str(ticket.description))
        self.assertEqual(ticket.last_reply_by, 'customer')
        self.assertEqual(ticket.stage_id, self.stage_new, "the customer's first mail does not move the ticket")
        # support answers -> waiting on customer
        ticket.with_user(self.agent1).message_post(body='Can you restart it?', message_type='comment',
                                                   subtype_xmlid='mail.mt_comment')
        self.assertEqual(ticket.last_reply_by, 'staff')
        self.assertEqual(ticket.stage_id, self.stage_waiting)
        # an internal note changes nothing
        ticket.with_user(self.agent1).message_post(body='internal', message_type='comment', subtype_xmlid='mail.mt_note')
        self.assertEqual(ticket.last_reply_by, 'staff')
        # the customer answers by e-mail -> in progress
        reply_id = self._process('Re: My screen is black', 'new.person@example.com', 'Still black.',
                                 '<reply-1@example.com>', extra='In-Reply-To: <first-1@example.com>\n')
        self.assertEqual(reply_id, ticket.id, 'the reply is attached to the ticket')
        self.assertEqual(ticket.last_reply_by, 'customer')
        self.assertTrue(ticket.date_last_customer_reply)
        self.assertEqual(ticket.stage_id, self.stage_progress)

    def test_closed_ticket_stays_closed(self):
        ticket = self._ticket()
        ticket.with_user(self.agent1).message_post(body='Done', message_type='comment', subtype_xmlid='mail.mt_comment')
        ticket.action_close()
        ticket.with_user(self.env.ref('base.public_user')).sudo().message_post(
            body='Thanks!', author_id=self.customer.id, message_type='comment', subtype_xmlid='mail.mt_comment')
        self.assertEqual(ticket.last_reply_by, 'customer')
        self.assertEqual(ticket.stage_id, self.stage_solved)

    def test_stage_templates_and_rating(self):
        ticket = self._ticket()
        self.env.cr.precommit.run()
        received = ticket.message_ids.filtered(lambda m: 'we received your request' in (m.subject or ''))
        self.assertEqual(len(received), 1, 'acknowledgement sent on creation')
        ticket.resolution = '<p>Replaced the toner.</p>'
        ticket.stage_id = self.stage_solved
        self.env.cr.precommit.run()
        solved = ticket.message_ids.filtered(lambda m: 'solved' in (m.subject or ''))
        self.assertEqual(len(solved), 1)
        self.assertIn('Replaced the toner', solved.body)
        rating = self.env['rating.rating'].search([('res_model', '=', 'support.ticket'), ('res_id', '=', ticket.id)])
        self.assertEqual(rating.partner_id, self.customer)
        self.assertIn(f'/rate/{rating.access_token}/5', solved.body)
        ticket.rating_apply(5, token=rating.access_token, feedback='Great')
        self.assertEqual(ticket.rating_last_value, 5)
        self.assertTrue(ticket.is_closed, 'a rating does not reopen the ticket')
        # no rating links when the team does not use ratings
        self.team.use_rating = False
        other = self._ticket()
        other.stage_id = self.stage_solved
        self.env.cr.precommit.run()
        self.assertNotIn('/rate/', other.message_ids.filtered(lambda m: 'solved' in (m.subject or '')).body)

    def test_auto_close(self):
        self.team.auto_close_days = 5
        waiting = self._ticket()
        waiting.with_user(self.agent1).message_post(body='Any news?', message_type='comment',
                                                    subtype_xmlid='mail.mt_comment')
        recent = self._ticket(name='Recent')
        recent.with_user(self.agent1).message_post(body='Any news?', message_type='comment',
                                                   subtype_xmlid='mail.mt_comment')
        customer_last = self._ticket(name='Customer answered')
        customer_last.with_user(self.agent1).message_post(body='Q', message_type='comment',
                                                          subtype_xmlid='mail.mt_comment')
        customer_last.message_post(body='A', author_id=self.customer.id, message_type='comment',
                                   subtype_xmlid='mail.mt_comment')
        old = fields.Datetime.now() - timedelta(days=6)
        (waiting | customer_last).write({'date_last_staff_reply': old})
        self.env['support.ticket']._cron_auto_close()
        self.assertTrue(waiting.is_closed)
        self.assertIn('Closed automatically', waiting.message_ids[0].body)
        self.assertFalse(recent.is_closed)
        self.assertFalse(customer_last.is_closed)
