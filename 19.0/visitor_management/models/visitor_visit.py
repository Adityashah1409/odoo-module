import base64
import io
import secrets
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

PASS_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no 0/O, 1/I: easy to read and type


class VisitorVisit(models.Model):
    _name = 'visitor.visit'
    _description = 'Visit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'check_in desc, planned_date desc, id desc'
    _rec_names_search = ['name', 'visitor_name', 'visitor_company', 'pass_code']
    _primary_email = 'email'

    name = fields.Char('Reference', default='New', readonly=True, copy=False)
    pass_code = fields.Char(readonly=True, copy=False, index=True,
                            help='Given to the visitor: used at the kiosk and printed on the pass.')
    state = fields.Selection([
        ('planned', 'Expected'),
        ('on_site', 'On site'),
        ('done', 'Checked out'),
        ('cancel', 'Cancelled'),
    ], default='planned', required=True, tracking=True, index=True, group_expand=True)
    source = fields.Selection([
        ('backend', 'Reception'),
        ('kiosk', 'Kiosk'),
    ], 'Registered at', default='backend', readonly=True)

    visitor_name = fields.Char('Visitor', required=True, tracking=True)
    partner_id = fields.Many2one('res.partner', 'Contact', help='Existing contact, if any.')
    visitor_company = fields.Char('Visitor company')
    phone = fields.Char()
    email = fields.Char()
    guests = fields.Integer('People', default=1, help='Number of people in the group, the visitor included.')
    vehicle = fields.Char('Vehicle plate')

    host_id = fields.Many2one('hr.employee', 'Host', tracking=True,
                              domain="[('company_id', 'in', [company_id, False])]")
    host_user_id = fields.Many2one(related='host_id.user_id', string='Host user')
    department_id = fields.Many2one(related='host_id.department_id', store=True, string='Department')
    visit_type_id = fields.Many2one('visitor.visit.type', 'Visit type', tracking=True)
    category_id = fields.Many2one('visitor.visit.category', 'Category', tracking=True)
    escort = fields.Boolean(related='category_id.escort')
    destination_id = fields.Many2one('visitor.destination', 'Destination',
                                     domain="[('company_id', 'in', [company_id, False])]")
    purpose = fields.Char()
    note = fields.Text('Notes')

    planned_date = fields.Datetime('Expected on', tracking=True)
    check_in = fields.Datetime(readonly=True, copy=False)
    check_out = fields.Datetime(readonly=True, copy=False)
    duration = fields.Float(compute='_compute_duration', store=True, help='Hours on site.')
    overstay = fields.Boolean('Longer than usual', compute='_compute_overstay')
    auto_checked_out = fields.Boolean(readonly=True, copy=False,
                                      help='Checked out automatically because the visitor stayed past the limit.')
    invitation_sent = fields.Boolean(readonly=True, copy=False)

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    color = fields.Integer(related='visit_type_id.color')

    _check_out_after_check_in = models.Constraint(
        'CHECK(check_out IS NULL OR check_in IS NULL OR check_out >= check_in)',
        'The check-out cannot be before the check-in.',
    )
    _pass_code_unique = models.Constraint('UNIQUE(pass_code)', 'This pass code is already used.')

    @api.constrains('check_in', 'check_out')
    def _check_dates(self):
        for visit in self:
            if visit.check_in and visit.check_out and visit.check_out < visit.check_in:
                raise ValidationError(self.env._('The check-out cannot be before the check-in.'))

    @api.depends('check_in', 'check_out')
    def _compute_duration(self):
        for visit in self:
            if visit.check_in and visit.check_out:
                visit.duration = (visit.check_out - visit.check_in).total_seconds() / 3600
            else:
                visit.duration = 0

    @api.depends('state', 'check_in', 'visit_type_id.expected_hours')
    def _compute_overstay(self):
        now = fields.Datetime.now()
        for visit in self:
            hours = visit.visit_type_id.expected_hours
            visit.overstay = bool(visit.state == 'on_site' and hours and visit.check_in
                                  and now - visit.check_in > timedelta(hours=hours))

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        partner = self.partner_id
        if partner:
            self.visitor_name = partner.name if not partner.is_company else self.visitor_name
            self.visitor_company = partner.commercial_company_name or (partner.name if partner.is_company else False)
            self.phone = partner.phone or self.phone
            self.email = partner.email or self.email

    @api.model
    def _new_pass_code(self):
        while True:
            code = ''.join(secrets.choice(PASS_ALPHABET) for _i in range(6))
            if not self.sudo().with_context(active_test=False).search_count([('pass_code', '=', code)], limit=1):
                return code

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                company = self.env['res.company'].browse(vals.get('company_id')) or self.env.company
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code('visitor.visit') or 'New'
            vals.setdefault('pass_code', self._new_pass_code())
        return super().create(vals_list)

    # ------------------------------------------------------------------ flow

    def action_check_in(self):
        for visit in self:
            if visit.state != 'planned':
                raise UserError(self.env._('%s is not expected any more.', visit.name))
        self.write({'state': 'on_site', 'check_in': fields.Datetime.now(), 'check_out': False})
        self._notify_host()
        return True

    def action_check_out(self):
        for visit in self:
            if visit.state != 'on_site':
                raise UserError(self.env._('%s is not on site.', visit.name))
        self.write({'state': 'done', 'check_out': fields.Datetime.now()})
        return True

    def action_cancel(self):
        if any(visit.state == 'done' for visit in self):
            raise UserError(self.env._('A visit that is over cannot be cancelled.'))
        self.write({'state': 'cancel'})
        return True

    def action_reset(self):
        self.write({'state': 'planned', 'check_in': False, 'check_out': False, 'auto_checked_out': False})
        return True

    def _notify_host(self):
        for visit in self:
            if not visit.company_id.visitor_notify_host or not visit.host_id:
                continue
            contact = visit.host_id.sudo().work_contact_id
            if not contact:
                continue
            body = self.env._(
                '%(visitor)s%(company)s has arrived and is waiting for you%(place)s.',
                visitor=visit.visitor_name,
                company=f' ({visit.visitor_company})' if visit.visitor_company else '',
                place=self.env._(' at %s', visit.destination_id.name) if visit.destination_id else '',
            )
            # from the kiosk nobody is logged in: the message comes from the company
            author = visit.company_id.partner_id if self.env.user._is_public() else self.env.user.partner_id
            visit.sudo().message_post(
                body=body, partner_ids=contact.ids, author_id=author.id, subtype_xmlid='mail.mt_comment',
                message_type='comment', email_layout_xmlid='mail.mail_notification_light')

    def action_send_invitation(self):
        self.ensure_one()
        if not self.email:
            raise UserError(self.env._('Add the e-mail address of the visitor first.'))
        template = self.env.ref('visitor_management.mail_template_visitor_invitation')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_model': 'visitor.visit',
                'default_res_ids': self.ids,
                'default_template_id': template.id,
                'default_composition_mode': 'comment',
                'default_email_layout_xmlid': 'mail.mail_notification_light',
                'mark_visitor_invitation': True,
            },
        }

    def _message_post_after_hook(self, message, msg_vals):
        if self.env.context.get('mark_visitor_invitation'):
            self.filtered(lambda v: not v.invitation_sent).invitation_sent = True
        return super()._message_post_after_hook(message, msg_vals)

    def action_print_pass(self):
        return self.env.ref('visitor_management.action_report_visitor_pass').report_action(self)

    # ------------------------------------------------------------------ helpers

    def _pass_qr_src(self):
        """ QR code of the pass code as a data URI, for the printed pass. """
        self.ensure_one()
        import qrcode  # noqa: PLC0415 (only needed when printing)
        img = qrcode.make(self.pass_code or '', box_size=8, border=1)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

    @api.model
    def _cron_auto_check_out(self):
        now = fields.Datetime.now()
        for company in self.env['res.company'].search([('visitor_max_hours', '>', 0)]):
            limit = now - timedelta(hours=company.visitor_max_hours)
            visits = self.search([('company_id', '=', company.id), ('state', '=', 'on_site'),
                                  ('check_in', '<', limit)])
            for visit in visits:
                visit.write({'state': 'done', 'check_out': now, 'auto_checked_out': True})
                visit.message_post(body=self.env._('Checked out automatically after %s hours on site.',
                                                   company.visitor_max_hours))

    # ------------------------------------------------------------------ kiosk

    @api.model
    def action_open_kiosk(self):
        return {'type': 'ir.actions.act_url', 'url': self.env.company._visitor_kiosk_url(), 'target': 'new'}

    @api.model
    def _kiosk_find(self, company, pass_code, states):
        code = (pass_code or '').strip().upper().replace(' ', '')
        if not code:
            return self.browse()
        return self.sudo().search([('company_id', '=', company.id), ('pass_code', '=', code),
                                   ('state', 'in', states)], limit=1)

    @api.model
    def _kiosk_check_in(self, company, values):
        """ Check in from the kiosk: an invited visitor with a pass code, or a walk-in. """
        visit = self._kiosk_find(company, values.get('pass_code'), ['planned'])
        if values.get('pass_code') and not visit:
            raise ValidationError(self.env._('This pass code is not valid or was already used.'))
        if visit:
            visit.action_check_in()
            return visit
        name = (values.get('visitor_name') or '').strip()
        if not name:
            raise ValidationError(self.env._('Please enter your name.'))
        host = self.env['hr.employee'].sudo().browse(int(values.get('host_id') or 0)).exists()
        if not host or host.company_id not in (company, self.env['res.company']) or not host.visitor_kiosk_host:
            raise ValidationError(self.env._('Please choose the person you are visiting.'))
        visit_type = self.env['visitor.visit.type'].sudo().browse(int(values.get('visit_type_id') or 0)).exists()
        visit = self.sudo().with_company(company).create({
            'visitor_name': name[:128],
            'visitor_company': (values.get('visitor_company') or '').strip()[:128],
            'phone': (values.get('phone') or '').strip()[:64],
            'email': (values.get('email') or '').strip()[:128],
            'host_id': host.id,
            'visit_type_id': visit_type.id if visit_type.kiosk else False,
            'purpose': (values.get('purpose') or '').strip()[:256],
            'company_id': company.id,
            'source': 'kiosk',
        })
        visit.action_check_in()
        return visit

    @api.model
    def _kiosk_check_out(self, company, pass_code):
        visit = self._kiosk_find(company, pass_code, ['on_site'])
        if not visit:
            raise ValidationError(self.env._('No visitor on site with this pass code.'))
        visit.action_check_out()
        return visit
