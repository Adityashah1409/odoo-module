import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("partner_names_signup_tour", {
    url: "/web/signup",
    steps: () => [
        { trigger: "input[name=first_name]", run: "edit Lotte" },
        { trigger: "input[name=last_name]", run: "edit Janssens" },
        { trigger: "input[name=login]", run: "edit lotte@example.com" },
        { trigger: "input[name=password]", run: "edit Lotte-pass-2027!" },
        { trigger: "input[name=confirm_password]", run: "edit Lotte-pass-2027!" },
        { trigger: ".oe_signup_form button[type=submit]", run: "click", expectUnloadPage: true },
        { content: "Logged in after sign up", trigger: "body:not(:has(.oe_signup_form))" },
    ],
});
