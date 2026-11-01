import { Chatter } from "@mail/chatter/web_portal_project/chatter";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

patch(Chatter.prototype, {
    setup() {
        super.setup();
        this.state.chatterOrder = session.chatter_message_order === "asc" ? "asc" : "desc";
    },

    changeThread() {
        super.changeThread(...arguments);
        if (this.state.thread) {
            this.state.thread.chatterOldestFirst = this.state.chatterOrder === "asc";
        }
    },

    get chatterOrderLabel() {
        return this.state.chatterOrder === "asc" ? _t("Oldest first") : _t("Newest first");
    },

    get chatterOrderTitle() {
        return this.state.chatterOrder === "asc"
            ? _t("Oldest messages first. Click to show the newest first.")
            : _t("Newest messages first. Click to show the oldest first.");
    },

    async onClickChatterOrder() {
        const order = this.state.chatterOrder === "asc" ? "desc" : "asc";
        this.state.chatterOrder = order;
        session.chatter_message_order = order;
        const thread = this.state.thread;
        thread.chatterOldestFirst = order === "asc";
        this.env.services.orm.call("res.users", "chatter_set_message_order", [order]);
        if (order === "asc") {
            await thread.chatterLoadOldest();
        } else {
            await thread.chatterLoadNewest();
        }
    },
});
