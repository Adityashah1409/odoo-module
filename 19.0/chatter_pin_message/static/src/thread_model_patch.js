import { Thread } from "@mail/core/common/thread_model";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";

/** Pinned messages in the chatter of a record (channels keep Odoo's own pins). */
patch(Thread.prototype, {
    setup() {
        super.setup();
        /** @type {Object<number, {name: string, pinned_at: string}>} */
        this.chatterPinInfo = {};
    },

    get isChatterPinnable() {
        return Boolean(this.id && this.model && this.model !== "discuss.channel");
    },

    async fetchChatterPins() {
        if (!this.isChatterPinnable) {
            return;
        }
        const res = await this.store.env.services.orm.call(this.model, "chatter_pinned_messages", [
            [this.id],
        ]);
        this._chatterPinApply(res);
    },

    _chatterPinApply(res) {
        this.store.insert(res.store);
        Object.assign(this.chatterPinInfo, res.pinned_by);
    },

    async chatterTogglePin(message) {
        const pinned = !message.pinned_at;
        const res = await this.store.env.services.orm.call(
            this.model,
            "chatter_set_message_pin",
            [[this.id]],
            { message_id: message.id, pinned }
        );
        if (!pinned) {
            delete this.chatterPinInfo[message.id];
        }
        this._chatterPinApply(res);
        this.store.env.services.notification.add(
            pinned ? _t("Message pinned to the top of the chatter.") : _t("Message unpinned."),
            { type: "info" }
        );
    },
});
