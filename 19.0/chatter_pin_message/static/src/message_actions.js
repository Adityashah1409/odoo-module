import { registerMessageAction } from "@mail/core/common/message_actions";
import { _t } from "@web/core/l10n/translation";

const PINNABLE_TYPES = ["comment", "email", "email_outgoing"];

registerMessageAction("chatter-pin", {
    condition: ({ message, store, thread }) =>
        store.self_partner &&
        thread?.isChatterPinnable &&
        !message.isEmpty &&
        PINNABLE_TYPES.includes(message.message_type),
    icon: "fa fa-thumb-tack",
    name: ({ message }) => (message.pinned_at ? _t("Unpin") : _t("Pin")),
    onSelected: ({ message, thread }) => thread.chatterTogglePin(message),
    sequence: 65,
});
