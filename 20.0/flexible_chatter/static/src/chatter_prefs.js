import { proxy } from "@odoo/owl";
import { session } from "@web/session";

const initial = session.flexible_chatter || { position: "auto", width: 0, hidden: false };

/** Chatter layout of the current user, shared by every chatter and form. */
export const chatterPrefs = proxy({ ...initial });

export function applyChatterWidth() {
    const root = document.documentElement;
    if (chatterPrefs.width) {
        root.style.setProperty("--o-flexible-chatter-width", `${chatterPrefs.width}%`);
        root.classList.add("o_flexible_chatter_width");
    } else {
        root.style.removeProperty("--o-flexible-chatter-width");
        root.classList.remove("o_flexible_chatter_width");
    }
}

applyChatterWidth();
