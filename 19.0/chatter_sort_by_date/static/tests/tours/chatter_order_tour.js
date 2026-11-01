import { registry } from "@web/core/registry";

const FIRST = ".o-mail-Chatter .o-mail-Thread .o-mail-Message:first";

registry.category("web_tour.tours").add("chatter_sort_by_date_tour", {
    steps: () => [
        { content: "Newest first by default", trigger: `${FIRST}:contains(Note 35)` },
        { trigger: ".o_chatter_order_toggle:contains(Newest first)", run: "click" },
        { content: "The very first message comes first", trigger: `${FIRST}:contains(Note 01)` },
        { trigger: ".o_chatter_order_toggle:contains(Oldest first)" },
        { content: "Notes in chronological order", trigger: ".o-mail-Message:contains(Note 02)" },
    ],
});

registry.category("web_tour.tours").add("chatter_sort_by_date_remembered_tour", {
    steps: () => [
        { content: "The order chosen before is kept", trigger: `${FIRST}:contains(Note 01)` },
        { trigger: ".o_chatter_order_toggle:contains(Oldest first)", run: "click" },
        { content: "Back to newest first", trigger: `${FIRST}:contains(Note 35)` },
        { trigger: ".o_chatter_order_toggle:contains(Newest first)" },
    ],
});
