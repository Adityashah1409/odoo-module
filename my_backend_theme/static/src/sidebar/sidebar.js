import { Component, computed, onWillDestroy, proxy, signal, useEffect, usePlugin } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { UIPlugin } from "@web/core/ui/ui_plugin";
import { useBus, useService } from "@web/core/utils/hooks";
import { fuzzyLookup } from "@web/core/utils/search";
import { computeAppsAndMenuItems } from "@web/webclient/menus/menu_helpers";
import { getAppIcon } from "../js/app_icon";
import { ThemePlugin } from "../js/theme_plugin";

const MOUNTED_ATTRIBUTE = "data-mbt-sidebar-mounted";
const MAX_SEARCH_RESULTS = 30;

/**
 * Vertical navigation shown when the menu style is a sidebar style.
 *
 * It only reads menus from Odoo's menu service, so it shows exactly the menus
 * the server sent for this user (access rights are applied there), and opens
 * them through the same `selectMenu` the top bar uses.
 */
export class Sidebar extends Component {
    static template = "my_backend_theme.Sidebar";
    static components = {};

    theme = usePlugin(ThemePlugin);
    ui = usePlugin(UIPlugin);

    isVisible = computed(() => this.theme.hasSidebar() && !this.ui.isSmall());
    search = signal("");

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.state = proxy({
            expanded: {},
            currentActionId: null,
        });
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => this.updateCurrentAction());
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => this.updateCurrentAction());
        // The layout makes room for the sidebar only while it is shown.
        useEffect(() => {
            document.documentElement.toggleAttribute(MOUNTED_ATTRIBUTE, this.isVisible());
        });
        onWillDestroy(() => document.documentElement.removeAttribute(MOUNTED_ATTRIBUTE));
    }

    get style() {
        return this.theme.get("menu_style");
    }

    get isCollapsed() {
        return this.style === "icons" || this.theme.sidebarCollapsed();
    }

    get showSections() {
        return this.style === "sidebar";
    }

    get apps() {
        return this.menuService.getApps().map((app) => ({ ...app, iconInfo: getAppIcon(app) }));
    }

    get currentApp() {
        return this.menuService.getCurrentApp();
    }

    get currentAppSections() {
        const app = this.currentApp;
        return app ? this.menuService.getMenuAsTree(app.id).childrenTree : [];
    }

    get searchResults() {
        const query = this.search().trim();
        if (!query) {
            return null;
        }
        const { apps, menuItems } = computeAppsAndMenuItems(this.menuService.getMenuAsTree("root"));
        const matchingApps = fuzzyLookup(query, apps, (item) => item.label);
        const matchingItems = fuzzyLookup(query, menuItems, (item) => `${item.parents} / ${item.label}`);
        return [...matchingApps, ...matchingItems].slice(0, MAX_SEARCH_RESULTS);
    }

    updateCurrentAction() {
        this.state.currentActionId = this.actionService.currentController?.action?.id || null;
    }

    isActive(menu) {
        return Boolean(menu.actionID) && menu.actionID === this.state.currentActionId;
    }

    isExpanded(menu) {
        return this.state.expanded[menu.id] ?? true;
    }

    getHref(menu) {
        const url = `/odoo/${menu.actionPath || "action-" + menu.actionID}`;
        return odoo.debug ? `${url}?debug=${odoo.debug}` : url;
    }

    onMenuClick(ev, menu) {
        // Let the browser open modified clicks (new tab/window) itself.
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button === 1) {
            return;
        }
        ev.preventDefault();
        this.search.set("");
        this.menuService.selectMenu(this.menuService.getMenu(menu.id));
    }

    toggleSection(menu) {
        this.state.expanded[menu.id] = !this.isExpanded(menu);
    }

    toggleCollapsed() {
        this.theme.toggleSidebar();
    }

    onSearchKeydown(ev) {
        if (ev.key === "Escape") {
            this.search.set("");
        } else if (ev.key === "Enter") {
            const [first] = this.searchResults || [];
            if (first) {
                this.onMenuClick(ev, first);
            }
        }
    }
}

registry.category("main_components").add("my_backend_theme.Sidebar", { Component: Sidebar });
