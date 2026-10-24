import { Component, useListener, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ShortcutHelpDialog } from "./shortcut_help_dialog";

const SCREENS = {
    product: ["ProductScreen"],
    payment: ["PaymentScreen"],
    receipt: ["ReceiptScreen", "FeedbackScreen"],
    orders: ["TicketScreen"],
};
const NAMED = { " ": "space", esc: "escape", del: "delete" };
// keys that still work while typing in a field
const ALWAYS_ACTIVE = /^(f\d{1,2}|escape)$/;

/** KeyboardEvent -> "ctrl+alt+shift+key", the format stored on pos.shortcut. */
export function eventToKey(ev) {
    let key = (ev.key || "").toLowerCase();
    key = NAMED[key] || key;
    if (["control", "alt", "shift", "meta"].includes(key)) {
        return null;
    }
    const parts = [];
    if (ev.ctrlKey || ev.metaKey) {
        parts.push("ctrl");
    }
    if (ev.altKey) {
        parts.push("alt");
    }
    // shift is implied by symbols such as "?" or "+": only keep it for letters and named keys
    if (ev.shiftKey && (key.length > 1 || /[a-z0-9]/.test(key))) {
        parts.push("shift");
    }
    parts.push(key);
    return parts.join("+");
}

export function currentScreen(pos) {
    const router = pos.router;
    if (router && typeof router.currentScreen === "function") {
        return router.currentScreen();
    }
    return router?.state?.current || pos.mainScreen?.name;
}

function isEditable(target) {
    return (
        target &&
        (target.isContentEditable ||
            ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
    );
}

export class PosShortcuts extends Component {
    static template = xml`<t/>`;

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        useListener(window, "keydown", this.onKeydown.bind(this), { capture: true });
    }

    get shortcuts() {
        return this.pos.config._pos_shortcuts || [];
    }

    findShortcut(key, screen) {
        const specific = Object.entries(SCREENS).find(([, names]) => names.includes(screen));
        const screenType = specific ? specific[0] : null;
        return (
            this.shortcuts.find((s) => s.key === key && s.screen === screenType) ||
            this.shortcuts.find((s) => s.key === key && s.screen === "all")
        );
    }

    onKeydown(ev) {
        if (!this.shortcuts.length || ev.repeat) {
            return;
        }
        const key = eventToKey(ev);
        if (!key) {
            return;
        }
        const hasCommandModifier = key.includes("ctrl+") || key.includes("alt+");
        if (isEditable(ev.target) && !hasCommandModifier && !ALWAYS_ACTIVE.test(key)) {
            return;
        }
        if (document.querySelector(".modal")) {
            return; // let dialogs handle their own keys
        }
        const shortcut = this.findShortcut(key, currentScreen(this.pos));
        if (!shortcut) {
            return;
        }
        if (isEditable(ev.target) && key === "escape") {
            ev.target.blur();
        }
        const handled = this.run(shortcut);
        if (handled !== false) {
            ev.preventDefault();
            ev.stopPropagation();
        }
    }

    get order() {
        return this.pos.getOrder();
    }

    click(selector) {
        const element = document.querySelector(selector);
        if (!element || element.classList.contains("disabled") || element.disabled) {
            return false;
        }
        element.click();
        return true;
    }

    moveLine(step) {
        const order = this.order;
        const lines = order?.lines || [];
        if (!lines.length) {
            return false;
        }
        const selected = order.getSelectedOrderline();
        const index = Math.max(0, Math.min(lines.length - 1, lines.findIndex((l) => l.uuid === selected?.uuid) + step));
        order.selectOrderline(lines[index]);
        return true;
    }

    run(shortcut) {
        const pos = this.pos;
        const order = this.order;
        switch (shortcut.action) {
            case "pay":
                return order?.lines?.length ? (pos.pay(), true) : false;
            case "qty_mode":
                pos.numpadMode = "quantity";
                return true;
            case "discount_mode":
                pos.numpadMode = "discount";
                return true;
            case "price_mode":
                pos.numpadMode = "price";
                return true;
            case "search_product": {
                const input = document.querySelector(
                    ".pos-topheader input, .pos-search-bar input, .search-bar-container input"
                );
                if (!input) {
                    return false;
                }
                input.focus();
                input.select?.();
                return true;
            }
            case "delete_line": {
                const line = order?.getSelectedOrderline();
                if (!line) {
                    return false;
                }
                order.removeOrderline(line);
                return true;
            }
            case "line_up":
                return this.moveLine(-1);
            case "line_down":
                return this.moveLine(1);
            case "payment_method": {
                const method = pos.models["pos.payment.method"].get(shortcut.payment_method_id);
                if (!method || !order) {
                    return false;
                }
                order.addPaymentline(method);
                return true;
            }
            case "remove_payment": {
                const line = order?.getSelectedPaymentline();
                if (!line) {
                    return false;
                }
                order.removePaymentline(line);
                return true;
            }
            case "validate":
                return this.click(".payment-screen .validation-button.next");
            case "next_order":
                return order ? (pos.orderDone(order), true) : false;
            case "new_order": {
                const newOrder = pos.addNewOrder();
                pos.navigate("ProductScreen", { orderUuid: newOrder.uuid });
                return true;
            }
            case "customer":
                pos.selectPartner();
                return true;
            case "orders":
                pos.navigate("TicketScreen");
                return true;
            case "back":
                if (currentScreen(pos) === "ProductScreen" || !order) {
                    return false;
                }
                pos.navigate("ProductScreen", { orderUuid: order.uuid });
                return true;
            case "help":
                this.dialog.add(ShortcutHelpDialog, { shortcuts: this.shortcuts });
                return true;
        }
        return false;
    }
}

registry.category("main_components").add("PosKeyboardShortcuts", { Component: PosShortcuts });
