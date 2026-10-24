import { Component, onWillStart, proxy } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const STATUS_LABELS = {
    booked: _t("Booked"),
    held: _t("On hold"),
    available: _t("Available"),
    blocked: _t("Blocked"),
};

export class SeatDashboard extends Component {
    static template = "event_seat_booking.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.statusLabels = STATUS_LABELS;
        this.state = proxy({ data: null });
        onWillStart(async () => {
            this.state.data = await this.orm.call("event.event", "get_seat_dashboard_data", []);
        });
    }

    money(value) {
        const { symbol, position } = this.state.data.currency;
        const text = Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return position === "before" ? `${symbol} ${text}` : `${text} ${symbol}`;
    }

    formatDate(value) {
        return value ? deserializeDateTime(value).toLocaleString({ year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
    }

    width(value, rows, key = "count") {
        const max = Math.max(1, ...rows.map((r) => r[key]));
        return `width: ${Math.round((value / max) * 100)}%`;
    }

    height(value) {
        const max = Math.max(1, ...this.state.data.days.map((d) => d.amount));
        return `height: ${Math.max(3, Math.round((value / max) * 100))}%`;
    }

    statusShare(count) {
        const total = this.state.data.status.reduce((sum, s) => sum + s.count, 0) || 1;
        return `flex: ${count / total}`;
    }

    openEvent(event) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "event.event",
            res_id: event.id,
            views: [[false, "form"]],
        });
    }

    openSeats(state) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Seats"),
            res_model: "event.seat",
            views: [[false, "list"]],
            domain: state ? [["state", "=", state], ["event_id.seat_booking", "=", true]] : [["event_id.seat_booking", "=", true]],
            context: { search_default_group_ticket: 1 },
        });
    }

    openRegistration(registration) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "event.registration",
            res_id: registration.id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("event_seat_booking.dashboard", SeatDashboard);
