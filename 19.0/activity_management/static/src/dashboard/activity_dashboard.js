import { Component, onWillStart, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const KPIS = [
    { key: "overdue", label: _t("Overdue"), icon: "fa-exclamation-circle", tone: "danger" },
    { key: "today", label: _t("Today"), icon: "fa-calendar-check-o", tone: "warning" },
    { key: "planned", label: _t("Planned"), icon: "fa-calendar", tone: "success" },
    { key: "done", label: _t("Done"), icon: "fa-check", tone: "info" },
    { key: "cancelled", label: _t("Cancelled"), icon: "fa-ban", tone: "muted" },
];

export class ActivityDashboard extends Component {
    static template = "activity_management.ActivityDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.kpis = KPIS;
        this.periods = [
            ["all", _t("Any date")],
            ["today", _t("Today")],
            ["week", _t("This week")],
            ["month", _t("This month")],
            ["last30", _t("Last 30 days")],
        ];
        this.state = useState({
            scope: "mine",
            period: "all",
            user_id: "",
            activity_type_id: "",
            res_model: "",
            tag_id: "",
            data: null,
            loading: true,
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        const s = this.state;
        this.state.data = await this.orm.call("mail.activity", "get_dashboard_data", [], {
            scope: s.scope,
            period: s.period,
            user_id: s.user_id || false,
            activity_type_id: s.activity_type_id || false,
            res_model: s.res_model || false,
            tag_id: s.tag_id || false,
        });
        this.state.loading = false;
    }

    setScope(scope) {
        this.state.scope = scope;
        this.state.user_id = "";
        this.load();
    }

    onFilter(field, ev) {
        this.state[field] = ev.target.value;
        this.load();
    }

    resetFilters() {
        Object.assign(this.state, { period: "all", user_id: "", activity_type_id: "", res_model: "", tag_id: "" });
        this.load();
    }

    barWidth(count, rows) {
        const max = Math.max(1, ...rows.map((r) => r.count));
        return `width: ${Math.round((count / max) * 100)}%`;
    }

    openKpi(kpi) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: kpi.label,
            res_model: "mail.activity",
            views: [[false, "list"], [false, "kanban"], [false, "form"]],
            domain: this.state.data.domains[kpi.key],
            context: { active_test: false },
        });
    }

    openActivity(activity) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "mail.activity",
            res_id: activity.id,
            views: [[false, "form"]],
            context: { active_test: false },
        });
    }

    openDocument(activity) {
        if (!activity.res_model) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: activity.res_model,
            res_id: activity.res_id,
            views: [[false, "form"]],
        });
    }

    async markDone(activity) {
        const action = await this.orm.call("mail.activity", "action_open_done_wizard", [[activity.id]]);
        await this.action.doAction(action, { onClose: () => this.load() });
    }

    async filterOnType(row) {
        this.state.activity_type_id = String(row.id);
        await this.load();
    }

    async filterOnUser(row) {
        if (this.state.scope === "mine") {
            return;
        }
        this.state.user_id = String(row.id);
        await this.load();
    }
}

registry.category("actions").add("activity_management.dashboard", ActivityDashboard);
