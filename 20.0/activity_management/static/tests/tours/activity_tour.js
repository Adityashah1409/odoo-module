import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("activity_management_tour", {
    steps: () => [
        {
            content: "The dashboard shows one activity due today",
            trigger: ".o_activity_dashboard .o_am_kpi[data-kpi='today'] .o_am_kpi_value:contains(1)",
        },
        {
            content: "Mark it as done from the table",
            trigger: ".o_am_row:contains(Tour call) .o_am_done",
            run: "click",
        },
        {
            content: "Write a feedback",
            trigger: ".modal .o_field_html[name='feedback'] .odoo-editor-editable",
            run: "editor Called from the tour",
        },
        {
            content: "Confirm",
            trigger: ".modal button[name='action_done']",
            run: "click",
        },
        {
            content: "The dashboard reloads: nothing left today",
            trigger: ".o_activity_dashboard .o_am_kpi[data-kpi='today'] .o_am_kpi_value:contains(0)",
        },
        {
            content: "Open the done activities",
            trigger: ".o_am_kpi[data-kpi='done']",
            run: "click",
        },
        {
            content: "The history list shows it",
            trigger: ".o_list_view .o_data_row:contains(Tour call)",
        },
    ],
});
