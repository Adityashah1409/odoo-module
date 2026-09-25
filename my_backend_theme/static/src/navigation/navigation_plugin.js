import { Plugin, signal, useEffect, useListener, usePlugin } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { router } from "@web/core/browser/router";
import { TitlePlugin } from "@web/core/browser/title_plugin";
import { GlobalBusPlugin } from "@web/core/global_bus_plugin";
import { ORM } from "@web/core/orm_plugin";
import { services } from "@web/core/services";
import { debounce } from "@web/core/utils/timing";
import { ActionPlugin } from "@web/webclient/actions/action_plugin";
import { logError, ThemePlugin } from "../js/theme_plugin";

const BOOKMARK_MODEL = "my.theme.bookmark";
const RECENT_MODEL = "my.theme.recent";
const QUICK_CREATE_MODEL = "my.theme.quick.create";

/** Backend URL of a record, understood by Odoo's router. */
export function recordUrl(resModel, resId) {
    return `/odoo/m-${encodeURIComponent(resModel)}/${Number(resId)}`;
}

/**
 * Navigate inside the web client exactly like a click on an internal link:
 * Odoo's router intercepts clicks on `/odoo/...` anchors.
 *
 * @param {string} url
 */
export function navigateTo(url) {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.hidden = true;
    document.body.append(anchor);
    try {
        anchor.click();
    } finally {
        anchor.remove();
    }
}

/**
 * Whether a click on a link should be left to the browser (new tab, new
 * window, download...) instead of navigating inside the web client.
 *
 * @param {MouseEvent} ev
 */
export function isModifiedClick(ev) {
    return ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey || ev.button !== 0;
}

/**
 * Handler for theme links (`<a href="/odoo/...">`). A plain click is left to
 * Odoo's router, which navigates without reloading. A modified click must not
 * reach the router, so the browser can open the link in a new tab.
 *
 * @param {MouseEvent} ev
 * @param {Function} [onNavigate] called for a plain click (e.g. close a menu)
 */
export function onThemeLinkClick(ev, onNavigate) {
    if (isModifiedClick(ev)) {
        ev.stopPropagation();
        return;
    }
    onNavigate?.();
}

/**
 * Data shared by the productivity features: quick create entries, bookmarks
 * and recently viewed records. Lists are loaded on first use and cached.
 *
 * Every server call goes through methods that check access rights; this
 * plugin only mirrors what the server returned for the current user.
 */
export class NavigationPlugin extends Plugin {
    theme = usePlugin(ThemePlugin);
    orm = usePlugin(ORM);
    action = usePlugin(ActionPlugin);
    bus = usePlugin(GlobalBusPlugin).bus;
    title = usePlugin(TitlePlugin);

    /** null while not loaded yet */
    quickCreateItems = signal(null);
    bookmarks = signal(null);
    recent = signal(null);

    lastTracked = "";

    setup() {
        const scheduleTracking = debounce(() => this.trackCurrentRecord(), 400);
        useListener(this.bus, "ACTION_MANAGER:UI-UPDATED", scheduleTracking);
        // Moving between records with the pager changes the title but does
        // not update the action manager's UI.
        useEffect(() => {
            this.title.title();
            scheduleTracking();
        });
    }

    /**
     * Description of the page the user is on.
     *
     * @returns {{ url: string, name: string, resModel: string|false, resId: number|false }}
     */
    getCurrentPage() {
        const controller = this.action.currentController;
        const state = router.current || {};
        const resModel = state.model || controller?.props?.resModel || false;
        const resId = Number.isInteger(state.resId)
            ? state.resId
            : controller?.props?.resId || false;
        const url = browser.location.pathname + browser.location.search;
        const name =
            controller?.displayName || this.title.title() || controller?.action?.name || url;
        return { url, name: String(name), resModel, resId: resId || false };
    }

    async trackCurrentRecord() {
        if (!this.theme.get("enable_recent")) {
            return;
        }
        const { resModel, resId } = this.getCurrentPage();
        if (!resModel || !Number.isInteger(resId)) {
            return;
        }
        const key = `${resModel},${resId}`;
        if (key === this.lastTracked) {
            return;
        }
        this.lastTracked = key;
        try {
            await this.orm.silent.call(RECENT_MODEL, "track", [resModel, resId]);
            // Refresh lazily: the next time the list is shown.
            this.recent.set(null);
        } catch (error) {
            logError("Could not remember the record.", error);
        }
    }

    async loadQuickCreateItems(force = false) {
        if (this.quickCreateItems() && !force) {
            return this.quickCreateItems();
        }
        const items = await this.orm.call(QUICK_CREATE_MODEL, "get_quick_create_items");
        this.quickCreateItems.set(items);
        return items;
    }

    async loadBookmarks(force = false) {
        if (this.bookmarks() && !force) {
            return this.bookmarks();
        }
        const bookmarks = await this.orm.call(BOOKMARK_MODEL, "get_bookmarks");
        this.bookmarks.set(bookmarks);
        return bookmarks;
    }

    async loadRecent(force = false) {
        if (this.recent() && !force) {
            return this.recent();
        }
        const recent = await this.orm.call(RECENT_MODEL, "get_recent");
        this.recent.set(recent);
        return recent;
    }

    isBookmarked(url) {
        return Boolean(this.bookmarks()?.some((bookmark) => bookmark.url === url));
    }

    /**
     * Bookmark the current page, or remove its bookmark.
     *
     * @returns {Promise<boolean>} whether the page is bookmarked afterwards
     */
    async toggleCurrentBookmark() {
        const page = this.getCurrentPage();
        const result = await this.orm.call(BOOKMARK_MODEL, "toggle_bookmark", [
            page.url,
            page.name,
            page.resModel || false,
            page.resId || false,
        ]);
        await this.loadBookmarks(true);
        return Boolean(result);
    }

    async removeBookmark(bookmarkId) {
        await this.orm.unlink(BOOKMARK_MODEL, [bookmarkId]);
        await this.loadBookmarks(true);
    }

    async clearRecent() {
        await this.orm.call(RECENT_MODEL, "clear_recent");
        this.recent.set([]);
    }

    /**
     * Open the creation form of a quick create entry in a dialog.
     *
     * @param {{ name: string, model: string, context: Object }} item
     */
    openQuickCreate(item) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            name: item.name,
            res_model: item.model,
            views: [[false, "form"]],
            target: "new",
            context: item.context || {},
        });
    }

    openRecord(resModel, resId) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openManageBookmarks() {
        return this.action.doAction("my_backend_theme.action_my_theme_bookmark");
    }
}

services.add(NavigationPlugin);
