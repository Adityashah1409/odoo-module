import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("login_as_user_tour", {
    url: "/odoo",
    steps: () => [
        {
            content: "Open the login as screen from the systray",
            trigger: ".o_login_as_open",
            run: "click",
        },
        {
            content: "Search the sales user",
            trigger: ".o_login_as_search",
            run: "edit Rita",
        },
        {
            content: "Pick her",
            trigger: ".o_login_as_user:contains(Rita Sales)",
            run: "click",
        },
        {
            content: "Her access is shown",
            trigger: ".o_login_as_selected_name:contains(Rita Sales)",
        },
        {
            content: "Give a reason",
            trigger: ".o_login_as_reason",
            run: "edit Ticket 42: cannot find the contacts menu",
        },
        {
            content: "Log in as Rita",
            trigger: ".o_login_as_submit:enabled",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "The banner shows who we are and the way back",
            trigger: ".o_login_as_pill:contains(Rita Sales) .o_login_as_back",
            run: "click",
            expectUnloadPage: true,
        },
        {
            content: "Back as the administrator",
            trigger: ".o_login_as_open",
        },
    ],
});
