import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("event_seat_booking_tour", {
    steps: () => [
        {
            content: "Ask for the two best seats",
            trigger: ".o_seat_best_button",
            run: "click",
        },
        {
            content: "Two seats are chosen",
            trigger: ".o_seat_selection li.o_seat_chosen:nth-child(2)",
        },
        {
            content: "Continue",
            trigger: ".o_seat_continue:enabled",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "First attendee",
            trigger: "input[name='1-name']",
            run: "edit Ada Lovelace",
        },
        {
            content: "First e-mail",
            trigger: "input[name='1-email']",
            run: "edit ada@example.com",
        },
        {
            content: "Second attendee",
            trigger: "input[name='2-name']",
            run: "edit Alan Turing",
        },
        {
            content: "Second e-mail",
            trigger: "input[name='2-email']",
            run: "edit alan@example.com",
        },
        {
            content: "Confirm",
            trigger: ".o_seat_confirm",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "Registration done",
            trigger: ".o_wereg_confirmed, h3:contains(Registration confirmed), :contains(confirmed)",
        },
    ],
});
