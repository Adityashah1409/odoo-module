import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("access_management_dashboard_tour", {
    steps: () => [
        {
            content: "The dashboard shows the rules",
            trigger: ".o_access_dashboard .o_amd_rules td:contains(Tour rule: no delete)",
        },
        {
            content: "Open the rule",
            trigger: ".o_amd_rules td:contains(Tour rule: no delete)",
            run: "click",
        },
        {
            content: "Models tab of the rule",
            trigger: ".o_form_view .o_notebook .nav-link:contains(Models)",
            run: "click",
        },
        {
            content: "The model line is there",
            trigger: ".o_form_view .o_field_widget[name=model_line_ids] .o_data_row:contains(No delete)",
        },
    ],
});

registry.category("web_tour.tours").add("access_management_pin_tour", {
    steps: () => [
        {
            content: "The menu asks for the code",
            trigger: ".o_am_pin .o_am_pin_input",
            run: "edit 1111",
        },
        {
            content: "Try a wrong code",
            trigger: ".o_am_pin_submit:enabled",
            run: "click",
        },
        {
            content: "Wrong code message",
            trigger: ".o_am_pin_error:contains(Wrong code)",
        },
        {
            content: "Type the right code",
            trigger: ".o_am_pin .o_am_pin_input",
            run: "edit 2468",
        },
        {
            content: "Unlock",
            trigger: ".o_am_pin_submit:enabled",
            run: "click",
        },
        {
            content: "The protected list opens",
            trigger: ".o_list_view .o_data_row:contains(Harbour Supplies)",
        },
        {
            content: "Select a record",
            trigger: ".o_list_view .o_data_row:contains(Harbour Supplies) .o_list_record_selector input",
            run: "click",
        },
        {
            content: "Open the action menu",
            trigger: ".o_control_panel button:contains(Actions)",
            run: "click",
        },
        {
            content: "Export is not offered (access rule), Duplicate still is",
            trigger: ".o-dropdown--menu:contains(Duplicate):not(:contains(Export))",
        },
    ],
});
