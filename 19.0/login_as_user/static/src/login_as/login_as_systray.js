import { Component, onWillUnmount, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";

export class LoginAsSystray extends Component {
    static template = "login_as_user.Systray";
    static props = {};

    setup() {
        this.action = useService("action");
        this.info = session.login_as || {};
        this.userName = user.name;
        this.state = useState({ remaining: this.info.remaining || 0, busy: false });
        if (this.info.origin) {
            document.body.classList.add("o_login_as_active");
            if (this.info.remaining) {
                const started = Date.now();
                const total = this.info.remaining;
                this.timer = browser.setInterval(() => {
                    this.state.remaining = Math.max(total - Math.floor((Date.now() - started) / 1000), 0);
                    if (!this.state.remaining) {
                        this.back();
                    }
                }, 1000);
                onWillUnmount(() => browser.clearInterval(this.timer));
            }
        }
    }

    get remainingLabel() {
        const s = this.state.remaining;
        const m = Math.floor(s / 60);
        return `${m}:${String(s % 60).padStart(2, "0")}`;
    }

    openSwitch() {
        this.action.doAction("login_as_user.action_login_as_switch");
    }

    async back() {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        browser.clearInterval(this.timer);
        const result = await rpc("/login_as/stop");
        browser.location.href = result.url || "/odoo";
    }
}

registry.category("systray").add(
    "login_as_user.systray",
    {
        Component: LoginAsSystray,
        isDisplayed: () => Boolean(session.login_as && (session.login_as.origin || session.login_as.can)),
    },
    { sequence: 1 }
);
