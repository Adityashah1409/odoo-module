from urllib.parse import quote

from markupsafe import escape

from odoo import api, fields, models


class PowerBIReport(models.Model):
    """A Power BI report shown inside Odoo (secure embed: users sign in with their Power BI account)."""
    _name = 'powerbi.report'
    _description = 'Power BI Report'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    report_url = fields.Char(
        "Report link", required=True,
        help="Power BI › open the report › File › Embed report › Website or portal (secure), "
             "or simply the report address from the browser.")
    tenant_id = fields.Char("Tenant ID", help="Optional: makes sign-in go straight to your organization.")
    group_ids = fields.Many2many('res.groups', string="Visible to",
                                 help="Leave empty for every Power BI user in Odoo.")
    height = fields.Integer(default=760)
    embed_url = fields.Char(compute='_compute_embed')
    embed_html = fields.Html(compute='_compute_embed', sanitize=False)

    @api.depends('report_url', 'tenant_id', 'height')
    def _compute_embed(self):
        for report in self:
            url = (report.report_url or '').strip()
            if url and 'reportEmbed' not in url and '/reports/' in url:
                # https://app.powerbi.com/groups/<g>/reports/<r>/... -> secure embed URL
                parts = url.split('/')
                report_id = parts[parts.index('reports') + 1] if 'reports' in parts else ''
                group_id = parts[parts.index('groups') + 1] if 'groups' in parts else ''
                url = f"https://app.powerbi.com/reportEmbed?reportId={report_id}"
                if group_id and group_id != 'me':
                    url += f"&groupId={group_id}"
                url += "&autoAuth=true"
            if url and report.tenant_id and 'ctid=' not in url:
                url += f"&ctid={quote(report.tenant_id)}"
            report.embed_url = url or False
            report.embed_html = (
                f'<iframe title="{escape(report.name)}" src="{escape(url)}" style="width:100%;height:{report.height or 760}px;'
                'border:0;border-radius:8px" allowfullscreen="true"></iframe>') if url else False
