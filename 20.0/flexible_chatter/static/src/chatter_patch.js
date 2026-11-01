import { Chatter } from "@mail/chatter/web_portal_project/chatter";
import { useListener } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

import { applyChatterWidth, chatterPrefs } from "./chatter_prefs";

const MIN_WIDTH = 20;
const MAX_WIDTH = 65;

patch(Chatter, {
    components: { ...Chatter.components, Dropdown, DropdownItem },
});

patch(Chatter.prototype, {
    setup() {
        super.setup();
        this.chatterPrefs = chatterPrefs;
        useListener(document, "mousedown", (ev) => this.onFlexibleChatterMouseDown(ev));
    },

    get chatterPositions() {
        return [
            { id: "auto", label: _t("Automatic") },
            { id: "side", label: _t("On the side") },
            { id: "bottom", label: _t("Below the form") },
        ];
    },

    saveChatterPrefs(values) {
        session.flexible_chatter = { ...chatterPrefs };
        return this.env.services.orm.call("res.users", "flexible_chatter_save", [values]);
    },

    setChatterPosition(position) {
        chatterPrefs.position = position;
        chatterPrefs.hidden = false;
        this.saveChatterPrefs({ position, hidden: false });
        // the form decides the layout on resize: let it compute it again
        browser.dispatchEvent(new Event("resize"));
    },

    toggleChatterHidden() {
        chatterPrefs.hidden = !chatterPrefs.hidden;
        this.saveChatterPrefs({ hidden: chatterPrefs.hidden });
    },

    resetChatterWidth() {
        chatterPrefs.width = 0;
        applyChatterWidth();
        this.saveChatterPrefs({ width: 0 });
    },

    /** Drag the left edge of the chatter on the side to change its width. */
    onFlexibleChatterMouseDown(ev) {
        const container = ev.target;
        if (
            !(container instanceof HTMLElement) ||
            !container.matches(".o-mail-Form-chatter.o-aside") ||
            ev.offsetX > 8 ||
            !this.rootRef() ||
            !container.contains(this.rootRef())
        ) {
            return;
        }
        ev.preventDefault();
        const parentRect = container.parentElement.getBoundingClientRect();
        const root = document.documentElement;
        const onMove = (moveEv) => {
            const width = Math.round(((parentRect.right - moveEv.clientX) / parentRect.width) * 100);
            chatterPrefs.width = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, width));
            applyChatterWidth();
        };
        const onUp = () => {
            document.removeEventListener("mousemove", onMove);
            document.removeEventListener("mouseup", onUp);
            root.classList.remove("o_flexible_chatter_resizing");
            this.saveChatterPrefs({ width: chatterPrefs.width });
        };
        root.classList.add("o_flexible_chatter_resizing");
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
    },
});
