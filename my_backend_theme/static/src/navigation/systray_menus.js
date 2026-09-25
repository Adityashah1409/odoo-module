import { Component, onMounted, onWillUnmount, proxy, usePlugin } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownGroup } from "@web/core/dropdown/dropdown_group";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { logError, startupConfig, ThemePlugin } from "../js/theme_plugin";
import { NavigationPlugin, onThemeLinkClick, recordUrl } from "./navigation_plugin";

/**
 * Register a configurable global shortcut for the lifetime of a component.
 *
 * @param {string|false} hotkey e.g. "alt+shift+n", or false when turned off
 * @param {Function} callback
 */
export function useThemeHotkey(hotkey, callback) {
    const hotkeyService = useService("hotkey");
    let remove = null;
    onMounted(() => {
        if (!hotkey) {
            return;
        }
        try {
            remove = hotkeyService.add(hotkey, callback, {
                global: true,
                // Work while a text field has the focus, except for
                // alt+control: AltGr sends it to type characters on many
                // keyboard layouts.
                bypassEditableProtection: !(hotkey.includes("alt+") && hotkey.includes("control+")),
            });
        } catch (error) {
            logError(`Invalid shortcut ${hotkey}.`, error);
        }
    });
    onWillUnmount(() => remove?.());
}

class ThemeSystrayMenu extends Component {
    static components = { Dropdown, DropdownGroup };

    setup() {
        this.theme = usePlugin(ThemePlugin);
        this.navigation = usePlugin(NavigationPlugin);
        this.dropdown = useDropdownState();
        this.state = proxy({ loading: false, error: false, currentUrl: "" });
        useThemeHotkey(this.theme.get(this.constructor.shortcutKey), () => {
            if (this.dropdown.isOpen) {
                this.dropdown.close();
            } else {
                this.dropdown.open();
            }
        });
    }

    get shortcut() {
        return this.theme.get(this.constructor.shortcutKey) || "";
    }

    get title() {
        const shortcut = this.shortcut;
        return shortcut ? `${this.constructor.label} (${shortcut.toUpperCase()})` : this.constructor.label;
    }

    /** Load the menu's data; errors are shown in the menu, not raised. */
    async onBeforeOpen() {
        this.state.loading = true;
        this.state.error = false;
        try {
            await this.load();
        } catch (error) {
            this.state.error = true;
            logError(`Could not load ${this.constructor.label}.`, error);
        } finally {
            this.state.loading = false;
        }
    }

    async load() {}

    close() {
        this.dropdown.close();
    }

    onLinkClick(ev) {
        onThemeLinkClick(ev, () => this.close());
    }
}

export class QuickCreateMenu extends ThemeSystrayMenu {
    static template = "my_backend_theme.QuickCreateMenu";
    static shortcutKey = "shortcut_quick_create";
    static label = _t("Quick Create");

    get items() {
        return this.navigation.quickCreateItems() || [];
    }

    load() {
        return this.navigation.loadQuickCreateItems();
    }

    onItemClick(item) {
        this.close();
        this.navigation.openQuickCreate(item);
    }
}

export class BookmarksMenu extends ThemeSystrayMenu {
    static template = "my_backend_theme.BookmarksMenu";
    static shortcutKey = "shortcut_bookmarks";
    static label = _t("Bookmarks");

    get bookmarks() {
        return this.navigation.bookmarks() || [];
    }

    get isCurrentBookmarked() {
        return this.navigation.isBookmarked(this.state.currentUrl);
    }

    load() {
        this.state.currentUrl = this.navigation.getCurrentPage().url;
        return this.navigation.loadBookmarks();
    }

    async toggleCurrent() {
        try {
            await this.navigation.toggleCurrentBookmark();
            this.state.currentUrl = this.navigation.getCurrentPage().url;
        } catch (error) {
            this.state.error = true;
            logError("Could not update the bookmark.", error);
        }
    }

    async remove(bookmark) {
        try {
            await this.navigation.removeBookmark(bookmark.id);
        } catch (error) {
            logError("Could not remove the bookmark.", error);
        }
    }

    manage() {
        this.close();
        this.navigation.openManageBookmarks();
    }
}

export class RecentMenu extends ThemeSystrayMenu {
    static template = "my_backend_theme.RecentMenu";
    static shortcutKey = "shortcut_recent";
    static label = _t("Recently Viewed");

    get entries() {
        return this.navigation.recent() || [];
    }

    load() {
        return this.navigation.loadRecent();
    }

    getUrl(entry) {
        return recordUrl(entry.res_model, entry.res_id);
    }

    async clear() {
        try {
            await this.navigation.clearRecent();
        } catch (error) {
            logError("Could not clear the list.", error);
        }
    }
}

const systray = registry.category("systray");
systray.add(
    "my_backend_theme.recent",
    { Component: RecentMenu, isDisplayed: () => startupConfig().enable_recent },
    { sequence: 65 }
);
systray.add(
    "my_backend_theme.bookmarks",
    { Component: BookmarksMenu, isDisplayed: () => startupConfig().enable_bookmarks },
    { sequence: 66 }
);
systray.add(
    "my_backend_theme.quick_create",
    { Component: QuickCreateMenu, isDisplayed: () => startupConfig().enable_quick_create },
    { sequence: 67 }
);
