import { Component, onWillStart, useState } from "@odoo/owl";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class WarehouseCostDashboard extends Component {
    static template = "warehouse_avg_costing.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null });
        onWillStart(async () => {
            this.state.data = await this.orm.call("stock.warehouse.cost.dashboard", "get_data", []);
        });
    }

    money(value) {
        const { symbol, position } = this.state.data.currency;
        const text = Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return position === "before" ? `${symbol} ${text}` : `${text} ${symbol}`;
    }

    cost(value) {
        return Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    width(value, rows) {
        const max = Math.max(1, ...rows.map((row) => row.value));
        return `width: ${Math.max(2, Math.round((value / max) * 100))}%`;
    }

    formatDate(value) {
        return value ? deserializeDateTime(value).toLocaleString({ month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
    }

    openCosts(warehouseId) {
        const domain = warehouseId === undefined ? [] : [["warehouse_id", "=", warehouseId || false]];
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Warehouse Costs"),
            res_model: "stock.warehouse.cost",
            views: [[false, "list"], [false, "pivot"]],
            domain,
            context: { search_default_in_stock: 1 },
        });
    }

    openProduct(productId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Warehouse Costs"),
            res_model: "stock.warehouse.cost",
            views: [[false, "list"]],
            domain: [["product_id", "=", productId]],
        });
    }

    openHistory() {
        this.action.doAction("warehouse_avg_costing.action_stock_warehouse_cost_line");
    }

    openPending() {
        this.action.doAction("warehouse_avg_costing.action_stock_warehouse_cost_adjustment", {
            additionalContext: { search_default_to_approve: 1 },
        });
    }

    openReport() {
        this.action.doAction("warehouse_avg_costing.action_stock_warehouse_valuation_report");
    }
}

registry.category("actions").add("warehouse_avg_costing.dashboard", WarehouseCostDashboard);
