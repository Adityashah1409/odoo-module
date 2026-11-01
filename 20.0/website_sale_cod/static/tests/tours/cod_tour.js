import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("website_sale_cod_collect_tour", {
    steps: () => [
        {
            content: "Open the collect dialog",
            trigger: ".o_form_view button[name=action_collect_wizard]",
            run: "click",
        },
        {
            content: "Type a wrong code",
            trigger: ".modal .o_field_widget[name=code] input",
            run: "edit 000000",
        },
        {
            trigger: ".modal button[name=action_confirm]",
            run: "click",
        },
        {
            content: "The error is shown",
            trigger: ".modal .alert-danger:contains(Wrong delivery code)",
        },
        {
            content: "Type the customer's code",
            trigger: ".modal .o_field_widget[name=code] input",
            run: "edit 482913",
        },
        {
            trigger: ".modal button[name=action_confirm]",
            run: "click",
        },
        {
            content: "Collected",
            trigger: ".o_form_view .o_statusbar_status button.o_arrow_button_current:contains(Collected)",
        },
    ],
});
