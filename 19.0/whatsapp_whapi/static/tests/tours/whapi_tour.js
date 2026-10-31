import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("whatsapp_whapi_tour", {
    url: "/odoo/whatsapp",
    steps: () => [
        {
            content: "The chat with Anna is in the list",
            trigger: ".o_whapi_chat_item:contains(Anna Peeters)",
            run: "click",
        },
        {
            content: "Her message is shown",
            trigger: ".o_whapi_message:contains(Do you deliver on Saturday?)",
            run: "hover",
        },
        {
            content: "Open the message menu",
            trigger: ".o_whapi_message:contains(Do you deliver on Saturday?) .o_whapi_menu_btn",
            run: "click",
        },
        {
            content: "Reply",
            trigger: ".o_whapi_menu .dropdown-item:contains(Reply)",
            run: "click",
        },
        {
            content: "Type the answer",
            trigger: ".o_whapi_reply_bar",
        },
        {
            trigger: ".o_whapi_input",
            run: "edit Yes, from 9 to 12.",
        },
        {
            content: "Send",
            trigger: ".o_whapi_send_text",
            run: "click",
        },
        {
            content: "The answer is in the conversation, with the quote",
            trigger: ".o_out .o_whapi_message:contains(Yes, from 9 to 12.) .o_whapi_quote",
        },
    ],
});
