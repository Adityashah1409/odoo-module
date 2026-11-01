import { registry } from "@web/core/registry";

const MENU = ".o_flexible_chatter_menu";

registry.category("web_tour.tours").add("flexible_chatter_tour", {
    steps: () => [
        {
            content: "Automatic: on this screen size the chatter is below the form",
            trigger: ".o-mail-Form-chatter:not(.o-aside) .o-mail-Chatter-top",
        },
        { trigger: MENU, run: "click" },
        { trigger: ".o_flexible_chatter_position_side", run: "click" },
        {
            content: "The chatter moves to the side",
            trigger: ".o-mail-Form-chatter.o-aside .o-mail-Chatter-top",
        },
        { trigger: MENU, run: "click" },
        { trigger: ".o_flexible_chatter_hide", run: "click" },
        {
            content: "Folded: only the bar is left",
            trigger: ".o-mail-Form-chatter.o-aside .o_flexible_chatter_bar.o_collapsed",
        },
        { trigger: ".o-mail-Chatter:not(:has(.o-mail-Chatter-top:visible))" },
        { trigger: ".o_flexible_chatter_bar", run: "click" },
        { content: "Open again", trigger: ".o-mail-Chatter-top:visible" },
        { trigger: MENU, run: "click" },
        { trigger: ".o_flexible_chatter_position_bottom", run: "click" },
        {
            content: "Below the form",
            trigger: ".o-mail-Form-chatter:not(.o-aside) .o-mail-Chatter-top",
        },
    ],
});
