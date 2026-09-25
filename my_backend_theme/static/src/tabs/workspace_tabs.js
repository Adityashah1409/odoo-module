import {
    Component,
    computed,
    onWillUnmount,
    proxy,
    signal,
    useEffect,
    useListener,
    usePlugin,
} from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { TitlePlugin } from "@web/core/browser/title_plugin";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";
import { GlobalBusPlugin } from "@web/core/global_bus_plugin";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { UIPlugin } from "@web/core/ui/ui_plugin";
import { user } from "@web/core/user";
import { debounce } from "@web/core/utils/timing";
import { session } from "@web/session";
import { logError, ThemePlugin } from "../js/theme_plugin";
import { isModifiedClick, navigateTo, NavigationPlugin } from "../navigation/navigation_plugin";
import { useThemeHotkey } from "../navigation/systray_menus";
import { TabStore } from "./tab_store";

const HOME_URL = "/odoo";

function storageKeys() {
    const suffix = `${session.db || ""}:${user.userId}`;
    return { workspace: `mbt_tabs:${suffix}`, pinned: `mbt_pinned_tabs:${suffix}` };
}

function readJSON(storage, key) {
    try {
        return JSON.parse(storage.getItem(key) || "null");
    } catch {
        return null;
    }
}

/**
 * Workspace tabs shown below the navbar: every tab remembers a backend page,
 * so users can keep several records or lists at hand and switch between them
 * without losing their place.
 */
export class WorkspaceTabs extends Component {
    static template = "my_backend_theme.WorkspaceTabs";
    static components = { Dropdown, DropdownItem };

    setup() {
        this.theme = usePlugin(ThemePlugin);
        this.navigation = usePlugin(NavigationPlugin);
        this.ui = usePlugin(UIPlugin);
        this.title = usePlugin(TitlePlugin);
        const bus = usePlugin(GlobalBusPlugin).bus;

        this.isVisible = computed(() => this.theme.get("enable_tabs") && !this.ui.isSmall());
        this.version = signal(0);
        this.menu = useDropdownState();
        this.state = proxy({ menuTabId: null, dragId: null });

        this.keys = storageKeys();
        this.store = new TabStore({ maxTabs: this.theme.get("max_tabs") });
        this.store.load(readJSON(browser.sessionStorage, this.keys.workspace));
        this.store.mergePinned(readJSON(browser.localStorage, this.keys.pinned));

        const syncActiveTab = debounce(() => this.syncActiveTab(), 300);
        useListener(bus, "ACTION_MANAGER:UI-UPDATED", syncActiveTab);
        useListener(browser, "popstate", syncActiveTab);
        useEffect(() => {
            this.title.title();
            syncActiveTab();
        });
        useEffect(() => {
            document.documentElement.toggleAttribute("data-mbt-tabs-mounted", this.isVisible());
        });
        onWillUnmount(() => document.documentElement.removeAttribute("data-mbt-tabs-mounted"));

        useThemeHotkey(this.theme.get("enable_tabs") && this.theme.get("shortcut_new_tab"), () =>
            this.duplicate(this.store.activeId)
        );
    }

    get tabs() {
        this.version();
        return this.store.tabs;
    }

    get activeId() {
        this.version();
        return this.store.activeId;
    }

    get menuTab() {
        this.version();
        return this.store.getTab(this.state.menuTabId) || this.store.activeTab;
    }

    /** Persist and re-render after a change of the store. */
    commit() {
        this.version.set(this.version() + 1);
        try {
            browser.sessionStorage.setItem(
                this.keys.workspace,
                JSON.stringify(this.store.toJSON())
            );
            browser.localStorage.setItem(
                this.keys.pinned,
                JSON.stringify(this.store.pinnedTabs())
            );
        } catch (error) {
            logError("Could not save the tabs.", error);
        }
    }

    /** The active tab follows the page the user is on. */
    syncActiveTab() {
        if (!this.isVisible()) {
            return;
        }
        const page = this.navigation.getCurrentPage();
        if (this.store.updateActive(page.url, page.name)) {
            this.commit();
        }
    }

    tabTitle(tab) {
        return tab.title || _t("New tab");
    }

    onTabClick(ev, tab) {
        if (isModifiedClick(ev)) {
            // Let the browser open the page in a real browser tab.
            ev.stopPropagation();
            return;
        }
        if (tab.id === this.store.activeId) {
            ev.preventDefault();
            return;
        }
        this.syncActiveTab();
        this.store.activate(tab.id);
        this.commit();
        // Odoo's router handles the click on the link from here.
    }

    onTabAuxClick(ev, tab) {
        if (ev.button === 1) {
            // Middle click closes the tab, like in browsers.
            ev.preventDefault();
            this.close(tab.id);
        }
    }

    onTabContextMenu(ev, tab) {
        ev.preventDefault();
        this.state.menuTabId = tab.id;
        this.menu.open();
    }

    onMenuToggle() {
        this.state.menuTabId = null;
    }

    goTo(tab) {
        if (tab) {
            navigateTo(tab.url);
        }
    }

    newTab() {
        this.syncActiveTab();
        this.store.open(HOME_URL, _t("New tab"));
        this.commit();
        navigateTo(HOME_URL);
    }

    close(id) {
        const next = this.store.close([id]);
        this.commit();
        this.goTo(next);
    }

    closeOthers(id) {
        const next = this.store.closeOthers(id);
        this.commit();
        this.goTo(next);
    }

    closeToTheRight(id) {
        const next = this.store.closeToTheRight(id);
        this.commit();
        this.goTo(next);
    }

    closeAll() {
        const next = this.store.closeAll();
        this.commit();
        this.goTo(next);
    }

    duplicate(id) {
        this.syncActiveTab();
        const copy = this.store.duplicate(id);
        this.commit();
        this.goTo(copy);
    }

    togglePin(id) {
        this.store.togglePin(id);
        this.commit();
    }

    reload(id) {
        const tab = this.store.activate(id);
        this.commit();
        this.goTo(tab);
    }

    openInBrowserTab(tab) {
        browser.open(tab.url, "_blank", "noopener");
    }

    onDragStart(ev, tab) {
        this.state.dragId = tab.id;
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/uri-list", new URL(tab.url, browser.location.origin).href);
    }

    onDragOver(ev) {
        if (this.state.dragId) {
            ev.preventDefault();
        }
    }

    onDrop(ev, tab) {
        if (this.state.dragId) {
            ev.preventDefault();
            if (this.store.move(this.state.dragId, tab.id)) {
                this.commit();
            }
        }
        this.state.dragId = null;
    }

    onDragEnd() {
        this.state.dragId = null;
    }
}

registry.category("main_components").add("my_backend_theme.WorkspaceTabs", {
    Component: WorkspaceTabs,
});
