import { Component } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

const SCREEN_LABELS = {
    all: "All screens",
    product: "Product screen",
    payment: "Payment screen",
    receipt: "Receipt screen",
    orders: "Orders list",
};

export class ShortcutHelpDialog extends Component {
    static template = "pos_keyboard_shortcuts.ShortcutHelpDialog";
    static components = { Dialog };
    static props = { shortcuts: Array, close: Function };

    get groups() {
        const groups = [];
        for (const screen of Object.keys(SCREEN_LABELS)) {
            const shortcuts = this.props.shortcuts.filter((s) => s.screen === screen);
            if (shortcuts.length) {
                groups.push({ screen, label: SCREEN_LABELS[screen], shortcuts });
            }
        }
        return groups;
    }

    keyParts(key) {
        return key === "+" ? ["+"] : key.endsWith("++") ? [...key.slice(0, -2).split("+"), "+"] : key.split("+");
    }
}
