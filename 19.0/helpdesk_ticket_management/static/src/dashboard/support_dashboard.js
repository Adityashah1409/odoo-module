import { Component, onWillStart, useState } from "@odoo/owl";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const KPIS = [
    { key: "open", label: _t("Open"), icon: "fa-life-ring", tone: "primary" },
    { key: "unassigned", label: _t("Unassigned"), icon: "fa-user-times", tone: "warning" },
    { key: "urgent", label: _t("Urgent"), icon: "fa-bolt", tone: "danger" },
    { key: "sla_failed", label: _t("SLA failed"), icon: "fa-exclamation-triangle", tone: "danger" },
    { key: "sla_risk", label: _t("SLA due in 24h"), icon: "fa-hourglass-half", tone: "warning" },
    { key: "closed_today", label: _t("Closed today"), icon: "fa-check-circle", tone: "success" },
];

export class SupportDashboard extends Component {
    static template = "helpdesk_ticket_management.SupportDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.kpis = KPIS;
        this.priorityLabels = { 0: _t("Low"), 1: _t("Medium"), 2: _t("High"), 3: _t("Urgent") };
        this.state = useState({ scope: "teams", team_id: "", data: null });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("support.ticket", "get_dashboard_data", [], {
            scope: this.state.scope,
            team_id: this.state.team_id || false,
        });
    }

    setScope(scope) {
        this.state.scope = scope;
        this.load();
    }

    onTeam(ev) {
        this.state.team_id = ev.target.value;
        this.load();
    }

    formatDeadline(value) {
        return value ? formatDateTime(deserializeDateTime(value), { showSeconds: false }) : "";
    }

    width(count, rows) {
        const max = Math.max(1, ...rows.map((r) => r.count));
        return `width: ${Math.round((count / max) * 100)}%`;
    }

    dayHeight(count) {
        const max = Math.max(1, ...this.state.data.daily.map((d) => d.count));
        return `height: ${Math.max(4, Math.round((count / max) * 100))}%`;
    }

    openTickets(name, domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "support.ticket",
            views: [[false, "list"], [false, "kanban"], [false, "form"]],
            domain,
            context: { active_test: false },
        });
    }

    openKpi(kpi) {
        this.openTickets(kpi.label, this.state.data.domains[kpi.key]);
    }

    openStage(row) {
        this.openTickets(row.name, [...this.state.data.domains.open, ["stage_id", "=", row.id]]);
    }

    openTeam(row) {
        this.openTickets(row.name, [...this.state.data.domains.open, ["team_id", "=", row.id || false]]);
    }

    openUser(row) {
        this.openTickets(row.name, [...this.state.data.domains.open, ["user_id", "=", row.id || false]]);
    }

    openPriority(row) {
        this.openTickets(row.name, [...this.state.data.domains.open, ["priority", "=", row.key]]);
    }

    openTicket(ticket) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "support.ticket",
            res_id: ticket.id,
            views: [[false, "form"]],
        });
    }

    newTicket() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "support.ticket",
            views: [[false, "form"]],
            context: this.state.team_id ? { default_team_id: parseInt(this.state.team_id) } : {},
        });
    }
}

registry.category("actions").add("helpdesk_ticket_management.dashboard", SupportDashboard);
