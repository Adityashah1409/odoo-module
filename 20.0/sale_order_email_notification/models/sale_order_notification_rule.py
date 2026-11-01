from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize, email_split


class SaleOrderNotificationRule(models.Model):
    _name = 'sale.order.notification.rule'
    _description = 'Sales order notification rule'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company,
                                 help='Empty: all companies.')
    trigger = fields.Selection([
        ('create', 'New quotation'),
        ('confirm', 'Order confirmed'),
        ('cancel', 'Order cancelled'),
    ], required=True, default='confirm')
    channel = fields.Selection([
        ('all', 'All orders'),
        ('backend', 'Orders made in the back office'),
        ('website', 'eCommerce orders'),
    ], required=True, default='all',
        help='eCommerce orders are those with a website (requires the eCommerce app). New eCommerce carts never '
             'trigger "New quotation" rules.')
    team_ids = fields.Many2many('crm.team', string='Sales teams', help='Empty: all teams.')
    min_amount = fields.Monetary('Minimum total', currency_field='currency_id',
                                 help='Only orders from this total (in the company currency). 0: all orders.')
    currency_id = fields.Many2one(related='company_id.currency_id')

    user_ids = fields.Many2many('res.users', string='Users', domain=[('share', '=', False)])
    email_list = fields.Char('Other e-mail addresses', help='Separated by commas, e.g. orders@example.com')
    notify_salesperson = fields.Boolean('Salesperson of the order')
    notify_team_leader = fields.Boolean('Leader of the sales team')
    notify_customer = fields.Boolean('Customer')
    template_id = fields.Many2one(
        'mail.template', 'E-mail template', required=True, domain=[('model', '=', 'sale.order')],
        default=lambda self: self.env.ref('sale_order_email_notification.mail_template_order_notification',
                                          raise_if_not_found=False))
    customer_template_id = fields.Many2one(
        'mail.template', 'Customer e-mail template', domain=[('model', '=', 'sale.order')],
        help='Used for the customer; empty: the order confirmation of Odoo for confirmations, the internal '
             'template otherwise.')
    attach_pdf = fields.Boolean('Attach the order PDF')
    sent_count = fields.Integer('E-mails sent', readonly=True, copy=False)
    last_sent = fields.Datetime('Last sent', readonly=True, copy=False)

    @api.constrains('email_list')
    def _check_email_list(self):
        for rule in self:
            for email in email_split(rule.email_list or ''):
                if not email_normalize(email):
                    raise ValidationError(self.env._('"%s" is not a valid e-mail address.', email))
            if rule.email_list and not email_split(rule.email_list):
                raise ValidationError(self.env._('Write e-mail addresses separated by commas.'))

    def _matches(self, order):
        self.ensure_one()
        if self.company_id and order.company_id != self.company_id:
            return False
        if self.channel != 'all' and order._order_notification_channel() != self.channel:
            return False
        if self.team_ids and order.team_id not in self.team_ids:
            return False
        if self.min_amount:
            total = order.currency_id._convert(order.amount_total, order.company_id.currency_id, order.company_id,
                                               order.date_order or fields.Date.today())
            if order.company_id.currency_id.compare_amounts(total, self.min_amount) < 0:
                return False
        return True

    def _internal_recipients(self, order):
        """ (partners, e-mail addresses) of the people inside the company to notify. """
        self.ensure_one()
        users = self.user_ids
        if self.notify_salesperson:
            users |= order.user_id
        if self.notify_team_leader:
            users |= order.team_id.user_id
        users = users.filtered(lambda u: u.active and u.partner_id.email)
        emails = [email_normalize(e) for e in email_split(self.email_list or '')]
        known = set(users.partner_id.mapped('email_normalized'))
        return users.partner_id, [e for e in dict.fromkeys(emails) if e and e not in known]

    def _attachment(self, order):
        report = self.env.ref('sale.action_report_saleorder')
        content, _fmt = self.env['ir.actions.report'].sudo()._render_qweb_pdf(report, order.ids)
        return self.env['ir.attachment'].sudo().create({
            'name': '%s.pdf' % order.name.replace('/', '_'),
            'raw': content,
            'mimetype': 'application/pdf',
        })

    def _send(self, order):
        self.ensure_one()
        partners, emails = self._internal_recipients(order)
        attachment = self._attachment(order) if self.attach_pdf and (partners or emails or self.notify_customer) \
            else self.env['ir.attachment']
        sent_to = []
        if partners or emails:
            # not linked to the order: internal e-mails stay out of its chatter (and of the customer portal)
            values = {'recipient_ids': [(6, 0, partners.ids)], 'email_to': ','.join(emails),
                      'model': False, 'res_id': False}
            if attachment:
                values['attachment_ids'] = [(4, attachment.id)]
            self.template_id.sudo().with_context(order_notification_rule=self.name).send_mail(
                order.id, email_layout_xmlid='mail.mail_notification_light', email_values=values)
            sent_to += partners.mapped('name') + emails
        if self.notify_customer and order.partner_id.email:
            template = self.customer_template_id or (
                self.trigger == 'confirm' and self.env.ref('sale.mail_template_sale_confirmation',
                                                           raise_if_not_found=False)) or self.template_id
            values = {'recipient_ids': [(6, 0, order.partner_id.ids)]}
            if attachment:
                values['attachment_ids'] = [(4, attachment.id)]
            template.sudo().send_mail(order.id, email_layout_xmlid='mail.mail_notification_light',
                                      email_values=values)
            sent_to.append(order.partner_id.name)
        if sent_to:
            self.sudo().write({'sent_count': self.sent_count + len(sent_to), 'last_sent': fields.Datetime.now()})
            order.sudo().message_post(
                body=self.env._('Notification "%(rule)s" sent to %(who)s.', rule=self.name, who=', '.join(sent_to)),
                subtype_xmlid='mail.mt_note')
        return sent_to

    def action_test(self):
        """ Send the rule now for the last order, to check the e-mail. """
        self.ensure_one()
        order = self.env['sale.order'].search(
            [('company_id', 'in', (self.company_id or self.env.company).ids)], order='id desc', limit=1)
        if not order:
            raise ValidationError(self.env._('There is no sales order to test with.'))
        sent_to = self._send(order)
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success' if sent_to else 'warning',
            'message': self.env._('Test e-mail for %(order)s sent to %(who)s.', order=order.name,
                                  who=', '.join(sent_to)) if sent_to else self.env._('Nobody to notify.'),
        }}
