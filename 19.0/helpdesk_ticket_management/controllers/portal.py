from markupsafe import Markup

from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.fields import Domain
from odoo.http import request
from odoo.tools import plaintext2html

from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

PARAM = 'helpdesk_ticket_management.'


class SupportPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if 'support_ticket_count' in counters:
            Ticket = request.env['support.ticket']
            values['support_ticket_count'] = Ticket.search_count(self._support_ticket_domain()) \
                if Ticket.has_access('read') else 0
        return values

    def _support_ticket_domain(self):
        partner = request.env.user.partner_id
        return Domain('partner_id', 'child_of', [partner.commercial_partner_id.id]) | \
            Domain('message_partner_ids', 'in', [partner.id])

    @staticmethod
    def _support_can_create():
        return bool(request.env['ir.config_parameter'].sudo().get_param(PARAM + 'portal_create'))

    @http.route(['/my/tickets', '/my/tickets/page/<int:page>'], type='http', auth='user', website=True)
    def portal_my_tickets(self, page=1, sortby=None, filterby=None, search=None, search_in='all', **kw):
        Ticket = request.env['support.ticket']
        sortings = {
            'date': {'label': request.env._('Newest'), 'order': 'create_date desc, id desc'},
            'reference': {'label': request.env._('Reference'), 'order': 'number desc'},
            'stage': {'label': request.env._('Status'), 'order': 'stage_id, id desc'},
            'priority': {'label': request.env._('Priority'), 'order': 'priority desc, id desc'},
        }
        filters = {
            'open': {'label': request.env._('Open'), 'domain': [('is_closed', '=', False)]},
            'closed': {'label': request.env._('Closed'), 'domain': [('is_closed', '=', True)]},
            'all': {'label': request.env._('All'), 'domain': []},
        }
        inputs = {
            'all': {'input': 'all', 'label': request.env._('Search in all')},
            'name': {'input': 'name', 'label': request.env._('Subject')},
            'number': {'input': 'number', 'label': request.env._('Reference')},
        }
        sortby = sortby if sortby in sortings else 'date'
        filterby = filterby if filterby in filters else 'open'
        domain = self._support_ticket_domain() & Domain(filters[filterby]['domain'])
        if search:
            if search_in == 'name':
                domain &= Domain('name', 'ilike', search)
            elif search_in == 'number':
                domain &= Domain('number', 'ilike', search)
            else:
                domain &= Domain('name', 'ilike', search) | Domain('number', 'ilike', search)
        count = Ticket.search_count(domain)
        pager = portal_pager(url='/my/tickets', total=count, page=page, step=self._items_per_page,
                             url_args={'sortby': sortby, 'filterby': filterby, 'search': search, 'search_in': search_in})
        tickets = Ticket.search(domain, order=sortings[sortby]['order'], limit=self._items_per_page,
                                offset=pager['offset'])
        request.session['my_support_tickets_history'] = tickets.ids[:100]
        values = self._prepare_portal_layout_values()
        values.update({
            'tickets': tickets.sudo(), 'page_name': 'support_ticket', 'pager': pager, 'default_url': '/my/tickets',
            'searchbar_sortings': sortings, 'sortby': sortby, 'searchbar_filters': filters, 'filterby': filterby,
            'searchbar_inputs': inputs, 'search_in': search_in, 'search': search,
            'can_create': self._support_can_create(),
        })
        return request.render('helpdesk_ticket_management.portal_my_tickets', values)

    @http.route('/my/tickets/<int:ticket_id>', type='http', auth='public', website=True)
    def portal_my_ticket(self, ticket_id, access_token=None, report_type=None, download=False, **kw):
        try:
            ticket_sudo = self._document_check_access('support.ticket', ticket_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if report_type in ('html', 'pdf', 'text'):
            return self._show_report(model=ticket_sudo, report_type=report_type,
                                     report_ref='helpdesk_ticket_management.action_report_support_ticket',
                                     download=download)
        values = {'ticket': ticket_sudo, 'page_name': 'support_ticket_detail', 'created': kw.get('created')}
        values = self._get_page_view_values(ticket_sudo, access_token, values, 'my_support_tickets_history', False, **kw)
        return request.render('helpdesk_ticket_management.portal_my_ticket', values)

    @http.route('/my/tickets/new', type='http', auth='user', website=True, methods=['GET', 'POST'])
    def portal_ticket_new(self, **post):
        if not self._support_can_create():
            return request.redirect('/my/tickets')
        env = request.env
        teams = env['support.team'].sudo().search([('company_id', '=', env.user.company_id.id)])
        types = env['support.ticket.type'].sudo().search([])
        categories = env['support.category'].sudo().search([('parent_id', '=', False)])
        error = {}
        if request.httprequest.method == 'POST':
            subject = (post.get('name') or '').strip()
            description = (post.get('description') or '').strip()
            if not subject:
                error['name'] = env._('Give your request a subject.')
            if not description:
                error['description'] = env._('Describe your request.')
            files = request.httprequest.files.getlist('attachments')
            limit_mb = int(env['ir.config_parameter'].sudo().get_param(PARAM + 'max_attachment_mb') or 0)
            attachments = []
            for upload in files:
                if not upload or not upload.filename:
                    continue
                content = upload.read()
                if limit_mb and len(content) > limit_mb * 1024 * 1024:
                    error['attachments'] = env._('%(file)s is larger than %(limit)s MB.', file=upload.filename,
                                                 limit=limit_mb)
                    break
                attachments.append((upload.filename, content, upload.mimetype))
            if not error:
                partner = env.user.partner_id
                vals = {
                    'name': subject,
                    'description': plaintext2html(description),
                    'partner_id': partner.id,
                    'channel': 'portal',
                    'priority': post.get('priority') if post.get('priority') in ('0', '1', '2', '3') else '0',
                }
                for field, records in (('team_id', teams), ('type_id', types), ('category_id', categories)):
                    value = int(post.get(field) or 0)
                    if value in records.ids:
                        vals[field] = value
                ticket = env['support.ticket'].sudo().with_context(mail_create_nosubscribe=True).create(vals)
                if attachments:
                    attachment_ids = env['ir.attachment'].sudo().create([{
                        'name': name, 'raw': content, 'mimetype': mimetype,
                        'res_model': 'support.ticket', 'res_id': ticket.id} for name, content, mimetype in attachments])
                    ticket.message_post(body=Markup('<p>%s</p>') % env._('Attachments from the customer.'),
                                        attachment_ids=attachment_ids.ids, author_id=partner.id,
                                        message_type='comment', subtype_xmlid='mail.mt_note')
                return request.redirect(f'/my/tickets/{ticket.id}?created=1')
        values = self._prepare_portal_layout_values()
        values.update({
            'page_name': 'support_ticket_new', 'teams': teams, 'types': types, 'categories': categories,
            'error': error, 'post': post,
        })
        return request.render('helpdesk_ticket_management.portal_ticket_new', values)
