import { registry } from "@web/core/registry";

const MSG = ".o-mail-Message:contains(Delivery window: Tuesdays 8-10 only)";

registry.category("web_tour.tours").add("chatter_pin_message_tour", {
    steps: () => [
        {
            content: "The record has two pinned messages already",
            trigger: ".o_chatter_pinned_bar:contains(2 pinned messages)",
        },
        {
            content: "Open the message actions",
            trigger: MSG,
            run: `hover && click ${MSG} [title='Expand']`,
        },
        {
            content: "Pin the message",
            trigger: "button[name='chatter-pin']:contains(Pin)",
            run: "click",
        },
        {
            content: "The bar counts three pinned messages",
            trigger: ".o_chatter_pinned_bar:contains(3 pinned messages)",
        },
        {
            content: "The message shows the pin icon",
            trigger: `${MSG} .o_chatter_pin_icon`,
        },
        {
            content: "Open the pinned list",
            trigger: ".o_chatter_pinned_toggle",
            run: "click",
        },
        {
            content: "Who pinned it is shown",
            trigger: ".o_chatter_pinned_item:contains(Delivery window):contains(Pinned by)",
        },
        {
            content: "Jump to the message",
            trigger: ".o_chatter_pinned_item:contains(Delivery window) .o_chatter_pinned_jump",
            run: "click",
        },
        {
            content: "Unpin it from the bar",
            trigger: ".o_chatter_pinned_item:contains(Delivery window) .o_chatter_pinned_unpin",
            run: "click",
        },
        {
            content: "Back to two pinned messages",
            trigger: ".o_chatter_pinned_bar:contains(2 pinned messages)",
        },
        {
            trigger: `${MSG}:not(:has(.o_chatter_pin_icon))`,
        },
    ],
});
