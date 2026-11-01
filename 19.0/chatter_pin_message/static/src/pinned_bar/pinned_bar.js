import { Component, onWillStart, onWillUpdateProps, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { formatDateTime } from "@web/core/l10n/dates";

/**
 * Bar on top of the chatter listing the pinned messages of the record.
 *
 * @typedef {Object} Props
 * @property {import("models").Thread} thread
 * @extends {Component<Props, Env>}
 */
export class ChatterPinnedBar extends Component {
    static template = "chatter_pin_message.PinnedBar";
    static props = ["thread"];

    setup() {
        this.state = useState({ open: false });
        onWillStart(() => {
            this.props.thread.fetchChatterPins();
        });
        onWillUpdateProps((nextProps) => {
            if (nextProps.thread.notEq(this.props.thread)) {
                this.state.open = false;
                nextProps.thread.fetchChatterPins();
            }
        });
    }

    get pinned() {
        // own stable order: Odoo's `pinnedMessages` sort never settles when two pins share the same second
        return this.props.thread.allMessages
            .filter((message) => message.pinned_at)
            .sort((m1, m2) => m2.pinned_at.toMillis() - m1.pinned_at.toMillis() || m2.id - m1.id);
    }

    get title() {
        const count = this.pinned.length;
        return count === 1 ? _t("1 pinned message") : _t("%s pinned messages", count);
    }

    pinnedByText(message) {
        const info = this.props.thread.chatterPinInfo[message.id];
        const when = message.pinned_at ? formatDateTime(message.pinned_at, { format: "DD" }) : "";
        if (info?.name) {
            return _t("Pinned by %(name)s on %(date)s", { name: info.name, date: when });
        }
        return _t("Pinned on %s", when);
    }

    toggle() {
        this.state.open = !this.state.open;
    }

    async onClickJump(message) {
        await this.env.messageHighlight?.highlightMessage(message, this.props.thread);
    }

    onClickUnpin(message) {
        return this.props.thread.chatterTogglePin(message);
    }
}
