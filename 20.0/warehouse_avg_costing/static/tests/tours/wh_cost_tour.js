import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("warehouse_avg_costing_tour", {
    steps: () => [
        {
            content: "Dashboard is loaded",
            trigger: ".o_wh_cost_dashboard .o_whc_kpi",
        },
        {
            content: "Open the valuation report",
            trigger: ".o_wh_cost_dashboard button:contains(Valuation report)",
            run: "click",
        },
        {
            content: "Choose the comparison",
            trigger: ".modal [name=report_type] input[data-value=comparison], .modal [name=report_type] label:contains(comparison)",
            run: "click",
        },
        {
            content: "View it",
            trigger: ".modal button[name=action_view]",
            run: "click",
        },
        {
            content: "Pivot of warehouse costs",
            trigger: ".o_pivot",
        },
    ],
});
