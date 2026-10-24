import { Component, useRef, useState, onMounted } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/** Shown instead of a PIN-protected menu's action until the right code is typed. */
export class PinPrompt extends Component {
    static template = "access_management.PinPrompt";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.params = this.props.action.params || {};
        this.state = useState({ code: "", error: "", busy: false });
        this.input = useRef("input");
        onMounted(() => this.input.el?.focus());
    }

    get isPin() {
        return this.params.pin_type !== "passphrase";
    }

    async submit(ev) {
        ev?.preventDefault();
        if (!this.state.code || this.state.busy) {
            return;
        }
        this.state.busy = true;
        const result = await rpc("/access_management/unlock", { lock_id: this.params.lock_id, code: this.state.code });
        this.state.busy = false;
        if (result.ok) {
            await this.action.doAction(this.params.action_id, { clearBreadcrumbs: true });
        } else {
            this.state.error = result.message;
            this.state.code = "";
            this.input.el?.focus();
        }
    }
}

registry.category("actions").add("access_management.pin_prompt", PinPrompt);
