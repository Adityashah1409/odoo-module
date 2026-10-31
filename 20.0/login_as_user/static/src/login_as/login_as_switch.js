import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useDebounced } from "@web/core/utils/timing";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

export class LoginAsSwitch extends Component {
    static template = "login_as_user.Switch";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        const params = this.props.action.params || {};
        this.state = proxy({
            term: "",
            users: [],
            selectedId: params.user_id || false,
            reason: "",
            requireReason: false,
            maxMinutes: 0,
            origin: "",
            loading: true,
            busy: false,
            error: "",
        });
        this.debouncedSearch = useDebounced(() => this.load(), 250);
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        const result = await this.orm.call("res.users", "login_as_search", [this.state.term], {
            limit: 40,
            user_id: this.state.selectedId,
        });
        const users = result.users;
        users.sort((a, b) => Number(b.recent) - Number(a.recent) || a.name.localeCompare(b.name));
        Object.assign(this.state, {
            users,
            requireReason: result.require_reason,
            maxMinutes: result.max_minutes,
            origin: result.origin,
            loading: false,
        });
        if (!this.state.selectedId && users.length === 1) {
            this.state.selectedId = users[0].id;
        }
    }

    get selected() {
        return this.state.users.find((u) => u.id === this.state.selectedId);
    }

    get canSubmit() {
        return this.selected && !this.state.busy && (!this.state.requireReason || this.state.reason.trim());
    }

    onSearch(ev) {
        this.state.term = ev.target.value;
        this.debouncedSearch();
    }

    onReason(ev) {
        this.state.reason = ev.target.value;
    }

    select(user) {
        this.state.selectedId = user.id;
        this.state.error = "";
    }

    initials(name) {
        return name
            .split(/\s+/)
            .slice(0, 2)
            .map((part) => part[0] || "")
            .join("")
            .toUpperCase();
    }

    async submit() {
        if (!this.canSubmit) {
            return;
        }
        this.state.busy = true;
        this.state.error = "";
        try {
            const result = await rpc("/login_as/start", {
                user_id: this.state.selectedId,
                reason: this.state.reason,
            });
            browser.location.href = result.url;
        } catch (error) {
            this.state.busy = false;
            this.state.error = error.data?.message || error.message || String(error);
        }
    }
}

registry.category("actions").add("login_as_user.switch", LoginAsSwitch);
