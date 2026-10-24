import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("hubspot_dashboard_tour", {
    steps: () => [
        {
            content: "Nothing synchronized yet",
            trigger: ".o_hubspot_dashboard .o_hs_linked .o_hs_value:contains(0)",
        },
        {
            content: "Synchronize the account",
            trigger: ".o_hubspot_dashboard .o_hs_sync:enabled",
            run: "click",
        },
        {
            content: "The company is linked",
            trigger: ".o_hubspot_dashboard .o_hs_linked .o_hs_value:contains(1)",
        },
        {
            content: "Open the companies",
            trigger: ".o_hs_objects tr:contains(Companies)",
            run: "click",
        },
        {
            content: "The link list shows it",
            trigger: ".o_list_view .o_data_row:contains(Tour Industries)",
        },
    ],
});
