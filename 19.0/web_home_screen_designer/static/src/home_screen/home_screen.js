import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";
import { computeAppsAndMenuItems } from "@web/webclient/menus/menu_helpers";

const LISTS = ["app_order", "hidden_apps"];

/** Apps in the saved order (unknown apps keep Odoo's order, after the ordered ones). */
export function orderApps(apps, order) {
    const rank = new Map((order || []).map((xmlid, index) => [xmlid, index]));
    return [...apps].sort((a, b) => {
        const ra = rank.has(a.xmlid) ? rank.get(a.xmlid) : order.length + apps.indexOf(a);
        const rb = rank.has(b.xmlid) ? rank.get(b.xmlid) : order.length + apps.indexOf(b);
        return ra - rb;
    });
}

export function greeting(hour) {
    if (hour < 5) {
        return _t("Good night");
    }
    if (hour < 12) {
        return _t("Good morning");
    }
    if (hour < 18) {
        return _t("Good afternoon");
    }
    return _t("Good evening");
}

export class HomeScreen extends Component {
    static template = "web_home_screen_designer.HomeScreen";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.menu = useService("menu");
        this.notification = useService("notification");
        this.state = useState({
            data: null,
            layout: {},
            saved: {},
            designer: false,
            search: "",
            now: new Date(),
            openOnLogin: false,
            allowUserLayout: true,
            busy: false,
        });
        const { apps, menuItems } = computeAppsAndMenuItems(this.menu.getMenuAsTree("root"));
        this.allApps = apps;
        this.menuItems = menuItems;
        onWillStart(() => this.load());
        onMounted(() => {
            this.timer = setInterval(() => (this.state.now = new Date()), 1000);
        });
        onWillUnmount(() => clearInterval(this.timer));
    }

    async load(promise) {
        const data = await (promise || this.orm.call("home.screen.layout", "get_home_screen", []));
        this.state.data = data;
        this.state.saved = JSON.parse(JSON.stringify(data.layout));
        this.state.layout = JSON.parse(JSON.stringify(data.layout));
        this.state.openOnLogin = data.open_on_login;
        this.state.allowUserLayout = data.allow_user_layout;
    }

    // ------------------------------------------------------------- display
    get layout() {
        return this.state.layout;
    }

    get apps() {
        const ordered = orderApps(this.allApps, this.layout.app_order || []);
        if (this.state.designer) {
            return ordered;
        }
        const hidden = new Set(this.layout.hidden_apps || []);
        return ordered.filter((app) => !hidden.has(app.xmlid));
    }

    get visibleApps() {
        const query = this.state.search.trim().toLowerCase();
        if (!query) {
            return this.apps;
        }
        return this.apps.filter((app) => app.label.toLowerCase().includes(query));
    }

    get menuResults() {
        const query = this.state.search.trim().toLowerCase();
        if (!query) {
            return [];
        }
        const hidden = new Set(this.layout.hidden_apps || []);
        const appXmlids = new Map(this.allApps.map((app) => [app.id, app.xmlid]));
        return this.menuItems
            .filter((item) => !hidden.has(appXmlids.get(item.appID)))
            .filter((item) => `${item.parents} / ${item.label}`.toLowerCase().includes(query))
            .slice(0, 8);
    }

    get rootStyle() {
        const l = this.layout;
        const vars = [
            `--hs-gap: ${l.gap}px`,
            `--hs-icon: ${l.icon_size}px`,
            `--hs-radius: ${l.icon_radius}%`,
            `--hs-font: ${l.font_size}px`,
            `--hs-overlay: ${(l.overlay_opacity || 0) / 100}`,
            `--hs-blur: ${l.blur}px`,
        ];
        if (l.columns) {
            vars.push(`--hs-columns: repeat(${l.columns}, minmax(0, 1fr))`);
        }
        if (l.background_type === "image" && this.backgroundUrl) {
            vars.push(`--hs-image: url('${this.backgroundUrl}')`);
        }
        return vars.join("; ");
    }

    get rootClass() {
        const l = this.layout;
        return [
            `o_hs_bg_${l.background_type}`,
            l.background_type === "gradient" ? `o_hs_gradient_${l.gradient}` : "",
            `o_hs_overlay_${l.overlay}`,
            `o_hs_tile_${l.tile_style}`,
            `o_hs_hover_${l.hover_effect}`,
            l.columns ? "o_hs_fixed_columns" : "",
            this.state.designer ? "o_hs_designing" : "",
        ].join(" ");
    }

    get backgroundUrl() {
        if (this.layout.background_image) {
            return `data:image/png;base64,${this.layout.background_image}`;
        }
        return this.layout.background_url;
    }

    get timeString() {
        const options = { hour: "2-digit", minute: "2-digit" };
        if (this.layout.show_seconds) {
            options.second = "2-digit";
        }
        return this.state.now.toLocaleTimeString(user.lang?.replace("_", "-") || undefined, options);
    }

    get dateString() {
        return this.state.now.toLocaleDateString(user.lang?.replace("_", "-") || undefined, {
            weekday: "long",
            day: "numeric",
            month: "long",
            year: "numeric",
        });
    }

    get greetingString() {
        return `${greeting(this.state.now.getHours())}, ${this.state.data.first_name}`;
    }

    iconStyle(app) {
        if (app.webIcon) {
            return `background-color: ${app.webIcon.backgroundColor}; color: ${app.webIcon.color};`;
        }
        return "";
    }

    iconClass(app) {
        return app.webIcon?.iconClass || app.webIcon?.icon || "";
    }

    isHidden(app) {
        return (this.layout.hidden_apps || []).includes(app.xmlid);
    }

    // ------------------------------------------------------------- actions
    openApp(app) {
        if (this.state.designer) {
            return;
        }
        this.menu.selectMenu(app.id);
    }

    openMenuItem(item) {
        this.menu.selectMenu(item.id);
    }

    onSearchKeydown(ev) {
        if (ev.key === "Enter") {
            const app = this.visibleApps[0];
            const item = this.menuResults[0];
            if (app) {
                this.openApp(app);
            } else if (item) {
                this.openMenuItem(item);
            }
        } else if (ev.key === "Escape") {
            this.state.search = "";
        }
    }

    // ------------------------------------------------------------ designer
    toggleDesigner() {
        this.state.designer = !this.state.designer;
        this.state.search = "";
    }

    setValue(name, value) {
        this.state.layout[name] = value;
    }

    setNumber(name, ev) {
        this.state.layout[name] = parseInt(ev.target.value, 10) || 0;
    }

    toggleApp(app) {
        const hidden = new Set(this.layout.hidden_apps || []);
        if (hidden.has(app.xmlid)) {
            hidden.delete(app.xmlid);
        } else {
            hidden.add(app.xmlid);
        }
        this.state.layout.hidden_apps = [...hidden];
    }

    moveApp(app, step) {
        const order = this.apps.map((a) => a.xmlid);
        const index = order.indexOf(app.xmlid);
        const target = index + step;
        if (target < 0 || target >= order.length) {
            return;
        }
        [order[index], order[target]] = [order[target], order[index]];
        this.state.layout.app_order = order;
    }

    onImageChange(ev) {
        const file = ev.target.files?.[0];
        if (!file) {
            return;
        }
        const reader = new FileReader();
        reader.onload = () => {
            this.state.layout.background_image = String(reader.result).split(",")[1];
            this.state.layout.background_type = "image";
        };
        reader.readAsDataURL(file);
    }

    payload() {
        const values = {};
        for (const [key, value] of Object.entries(this.layout)) {
            if (key === "background_url") {
                continue;
            }
            if (LISTS.includes(key) || JSON.stringify(value) !== JSON.stringify(this.state.saved[key])) {
                values[key] = value;
            }
        }
        return values;
    }

    async save(scope) {
        this.state.busy = true;
        try {
            const kwargs = { scope, open_on_login: this.state.openOnLogin };
            if (scope === "company") {
                kwargs.allow_user_layout = this.state.allowUserLayout;
            }
            await this.load(this.orm.call("home.screen.layout", "save_home_screen", [this.payload()], kwargs));
            this.state.designer = false;
            this.notification.add(
                scope === "company" ? _t("Company home screen saved.") : _t("Your home screen is saved."),
                { type: "success" }
            );
        } finally {
            this.state.busy = false;
        }
    }

    async resetToCompany() {
        await this.load(this.orm.call("home.screen.layout", "reset_home_screen", []));
        this.state.designer = false;
    }

    cancel() {
        this.state.layout = JSON.parse(JSON.stringify(this.state.saved));
        this.state.openOnLogin = this.state.data.open_on_login;
        this.state.allowUserLayout = this.state.data.allow_user_layout;
        this.state.designer = false;
    }
}

registry.category("actions").add("web_home_screen_designer.home", HomeScreen);
