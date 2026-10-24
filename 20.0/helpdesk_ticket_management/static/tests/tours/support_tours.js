import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("support_dashboard_tour", {
    steps: () => [
        {
            content: "One urgent ticket on the dashboard",
            trigger: ".o_support_dashboard .o_sd_kpi[data-kpi='urgent'] .o_sd_value:contains(1)",
        },
        {
            content: "Open the urgent tickets",
            trigger: ".o_sd_kpi[data-kpi='urgent']",
            run: "click",
        },
        {
            content: "Open the ticket",
            trigger: ".o_list_view .o_data_row:contains(Tour urgent ticket) .o_data_cell[name='name']",
            run: "click",
        },
        {
            content: "Assign it to me",
            trigger: ".o_form_view button[name='action_assign_to_me']",
            run: "click",
        },
        {
            content: "Start the timer",
            trigger: ".o_form_view button[name='action_timer_start']",
            run: "click",
        },
        {
            content: "The timer runs",
            trigger: ".o_form_view button[name='action_timer_stop']",
            run: "click",
        },
        {
            content: "Stopped",
            trigger: ".o_form_view button[name='action_timer_start']",
        },
    ],
});

registry.category("web_tour.tours").add("support_portal_tour", {
    steps: () => [
        {
            content: "New ticket",
            trigger: "a.o_support_new_ticket",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "Subject",
            trigger: "form.o_support_ticket_form input[name='name']",
            run: "edit Tour portal request",
        },
        {
            content: "Description",
            trigger: "form.o_support_ticket_form textarea[name='description']",
            run: "edit The printer on floor 2 jams.",
        },
        {
            content: "Submit",
            trigger: "form.o_support_ticket_form button[type='submit']",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "Confirmation",
            trigger: ".alert-success:contains(was created)",
        },
    ],
});
