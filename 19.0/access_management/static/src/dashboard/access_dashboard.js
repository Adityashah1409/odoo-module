import { Component, onWillStart, useState } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AccessDashboard extends Component {
    static template = "access_management.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("access.dashboard", "get_data", []);
    }

    bar(value, rows, key) {
        const max = Math.max(1, ...rows.map((row) => row[key]));
        return `width: ${Math.max(4, Math.round((value / max) * 100))}%`;
    }

    column(value) {
        const max = Math.max(1, ...this.state.data.days.map((d) => d.records));
        return `height: ${Math.max(4, Math.round((value / max) * 100))}%`;
    }

    formatDate(value) {
        return value
            ? deserializeDateTime(value).toLocaleString({ month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
            : "";
    }

    openRules(domain = [], name = _t("Access Rules")) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "access.rule",
            views: [[false, "list"], [false, "form"]],
            domain,
            context: { active_test: false },
        });
    }

    openRule(id) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "access.rule", res_id: id, views: [[false, "form"]] });
    }

    newRule() {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "access.rule", views: [[false, "form"]] });
    }

    openKind(key) {
        const domains = {
            menus: [["menu_ids", "!=", false]],
            models: [["model_line_ids", "!=", false]],
            fields: [["field_line_ids", "!=", false]],
            elements: [["element_line_ids", "!=", false]],
            readonly: [["readonly_user", "=", true]],
            login: ["|", "|", ["block_login", "=", true], ["block_api", "=", true], ["no_debug", "=", true]],
        };
        this.openRules([["is_effective", "=", true], ...domains[key]]);
    }

    openUser(id) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "res.users", res_id: id, views: [[false, "form"]] });
    }

    openExports(alerts = false) {
        this.action.doAction("access_management.action_access_export_log", {
            additionalContext: alerts ? { search_default_alerts: 1 } : {},
        });
    }

    openLocks() {
        this.action.doAction("access_management.action_access_menu_lock");
    }

    openAttempts() {
        this.action.doAction("access_management.action_access_lock_attempt", {
            additionalContext: { search_default_failed: 1 },
        });
    }

    openMap() {
        this.action.doAction("access_management.action_access_map");
    }

    async archiveExpired() {
        await this.action.doAction(await this.orm.call("access.rule", "action_archive_expired", []));
        await this.load();
    }

    async refreshCaches() {
        const action = await this.orm.call("access.rule", "action_refresh_cache", [[]]);
        delete action.params.next;
        await this.action.doAction(action);
        await this.load();
    }
}

registry.category("actions").add("access_management.dashboard", AccessDashboard);
