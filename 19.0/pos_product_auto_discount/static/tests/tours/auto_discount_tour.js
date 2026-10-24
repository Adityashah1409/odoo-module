import * as Chrome from "@point_of_sale/../tests/pos/tours/utils/chrome_util";
import * as Dialog from "@point_of_sale/../tests/generic_helpers/dialog_util";
import * as PaymentScreen from "@point_of_sale/../tests/pos/tours/utils/payment_screen_util";
import * as ProductScreen from "@point_of_sale/../tests/pos/tours/utils/product_screen_util";
import { registry } from "@web/core/registry";

const line = (name) => `.order-container .orderline:has(.product-name:contains("${name}"))`;

function assertEqual(actual, expected, label) {
    if (actual !== expected) {
        throw new Error(`${label}: expected ${expected}, got ${actual}`);
    }
}

registry.category("web_tour.tours").add("pos_auto_discount_tour", {
    steps: () =>
        [
            Chrome.startPoS(),
            Dialog.confirm("Open Register"),
            {
                content: "rule logic (dates, happy hours across midnight, categories with parents)",
                trigger: ".product-screen",
                run: () => {
                    const { bestRule, inHours, ruleMatchesProduct } = odoo.loader.modules.get(
                        "@pos_product_auto_discount/app/auto_discount"
                    );
                    const at = (h, m = 0) => new Date(2030, 5, 15, h, m);
                    const night = { hour_from: 22, hour_to: 2 };
                    assertEqual(inHours(night, at(23)), true, "23:00 in 22-02");
                    assertEqual(inHours(night, at(1, 30)), true, "01:30 in 22-02");
                    assertEqual(inHours(night, at(12)), false, "12:00 in 22-02");
                    assertEqual(inHours({ hour_from: 17, hour_to: 19 }, at(19)), false, "end excluded");
                    const parent = { id: 1 };
                    const product = { product_tmpl_id: { id: 7, pos_categ_ids: [{ id: 2, parent_id: parent }] } };
                    const categRule = { applies_on: "categories", pos_categ_ids: [1], product_tmpl_ids: [] };
                    assertEqual(ruleMatchesProduct(categRule, product), true, "parent category");
                    const rules = [
                        { id: 1, discount: 10, applies_on: "all", min_qty: 0 },
                        { id: 2, discount: 30, applies_on: "all", min_qty: 5 },
                        { id: 3, discount: 50, applies_on: "all", date_from: "2030-06-16" },
                    ];
                    assertEqual(bestRule(rules, product, 1, at(10)).id, 1, "qty 1");
                    assertEqual(bestRule(rules, product, 5, at(10)).id, 2, "qty 5");
                    assertEqual(bestRule(rules, product, 5, new Date(2030, 5, 16, 10)).id, 3, "from date");
                },
            },
            {
                content: "badge on the Desk Organizer card",
                trigger: 'article.product:has(.product-name:contains("Desk Organizer")) .o_pos_auto_discount_badge:contains("-10%")',
            },
            {
                content: "no badge for the expired rule on Letter Tray",
                trigger: 'article.product:has(.product-name:contains("Letter Tray")):not(:has(.o_pos_auto_discount_badge))',
            },
            ProductScreen.clickDisplayedProduct("Desk Organizer"),
            { content: "10% applied", trigger: `${line("Desk Organizer")} .price-per-unit em:contains("10%")` },
            { content: "rule name shown", trigger: `${line("Desk Organizer")} .o_pos_auto_discount_name:contains("Organizer promo")` },
            ProductScreen.clickDisplayedProduct("Desk Organizer"),
            ProductScreen.clickDisplayedProduct("Desk Organizer"),
            { content: "25% from 3 units", trigger: `${line("Desk Organizer")} .price-per-unit em:contains("25%")` },
            ProductScreen.clickDisplayedProduct("Letter Tray"),
            { content: "Letter Tray full price", trigger: `${line("Letter Tray")}:not(:has(.price-per-unit))` },
            ProductScreen.clickDisplayedProduct("Magnetic Board"),
            { content: "20% on Magnetic Board", trigger: `${line("Magnetic Board")} .price-per-unit em:contains("20%")` },
            // the cashier overrides the discount: it is kept when the quantity changes
            ProductScreen.addDiscount("5"),
            { content: "5% by hand", trigger: `${line("Magnetic Board")} .price-per-unit em:contains("5%")` },
            ProductScreen.clickNumpad("Qty", "2"),
            ProductScreen.selectedOrderlineHas("Magnetic Board", "2"),
            {
                content: "quantity 2, still 5% and no rule name",
                trigger: `${line("Magnetic Board")}:not(:has(.o_pos_auto_discount_name)) .price-per-unit em:contains("5%")`,
            },
            ProductScreen.clickPayButton(),
            PaymentScreen.clickPaymentMethod("Bank"),
            PaymentScreen.clickValidate(),
            { content: "order validated", trigger: ".receipt-screen, .feedback-screen" },
        ].flat(),
});
