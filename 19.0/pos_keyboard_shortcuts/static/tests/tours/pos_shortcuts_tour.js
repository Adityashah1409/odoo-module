import * as Chrome from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as ProductScreen from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import { registry } from "@web/core/registry";

function press(keys, trigger = "body") {
    return { content: `press ${keys}`, trigger, run: `press ${keys}` };
}

registry.category("web_tour.tours").add("pos_keyboard_shortcuts_tour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            ProductScreen.clickDisplayedProduct("Desk Organizer"),
            ProductScreen.clickDisplayedProduct("Letter Tray"),
            // help sheet
            press("f1", ".product-screen"),
            { content: "help is open", trigger: ".o_pos_shortcut_help:contains(Go to payment)" },
            { content: "close help", trigger: ".modal .btn-close", run: "click" },
            // move between lines and delete one
            press("arrowup", ".product-screen"),
            press("delete", ".product-screen"),
            {
                content: "one line left",
                trigger: ".order-container:has(.orderline):not(:has(.orderline ~ .orderline))",
            },
            // to payment, pay cash, validate
            press("shift+p", ".product-screen"),
            { content: "payment screen", trigger: ".payment-screen" },
            press("c", ".payment-screen"),
            { content: "cash line added", trigger: ".payment-screen .paymentline" },
            press("v", ".payment-screen"),
            { content: "order validated", trigger: ".receipt-screen, .feedback-screen" },
            press("n", ".receipt-screen, .feedback-screen"),
            { content: "back on products", trigger: ".product-screen" },
            // orders list and back
            press("shift+g", ".product-screen"),
            { content: "orders list", trigger: ".ticket-screen" },
            press("escape", ".ticket-screen"),
            { content: "back on products again", trigger: ".product-screen" },
        ].flat(),
});
