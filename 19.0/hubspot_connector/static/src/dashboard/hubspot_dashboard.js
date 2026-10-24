import { Component, onWillStart, useState } from "@odoo/owl";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class HubspotDashboard extends Component {
    static template = "hubspot_connector.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ account_id: "", data: null, busy: false });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call("hubspot.dashboard", "get_dashboard_data", [], {
            account_id: this.state.account_id || false,
        });
    }

    onAccount(ev) {
        this.state.account_id = ev.target.value;
        this.load();
    }

    formatDate(value) {
        return value ? formatDateTime(deserializeDateTime(value), { showSeconds: false }) : _t("Never");
    }

    barHeight(value) {
        const max = Math.max(1, ...this.state.data.days.map((d) => d.import + d.export));
        return `height: ${Math.round((value / max) * 100)}%`;
    }

    async syncNow(account) {
        this.state.busy = true;
        try {
            await this.orm.call("hubspot.account", "action_sync_now", [[account.id]]);
            this.notification.add(_t("Synchronization done for %s.", account.name), { type: "success" });
        } finally {
            this.state.busy = false;
            await this.load();
        }
    }

    openQueue(state) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Queue"),
            res_model: "hubspot.queue",
            views: [[false, "list"], [false, "form"]],
            domain: state ? [["state", "=", state]] : [],
        });
    }

    openLinks(object) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: object.label,
            res_model: "hubspot.record",
            views: [[false, "list"]],
            domain: [["object_type", "=", object.key]],
        });
    }

    openAccount(account) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hubspot.account",
            res_id: account.id,
            views: [[false, "form"]],
        });
    }

    openLog(log) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "hubspot.log",
            res_id: log.id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("hubspot_connector.dashboard", HubspotDashboard);
