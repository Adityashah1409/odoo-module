/**
 * Pure state handling of the workspace tabs, kept free of Odoo services so it
 * can be unit tested. A tab is `{ id, url, title, pinned }`.
 *
 * Each browser tab has its own workspace (sessionStorage, kept across
 * reloads). Pinned tabs are also saved in localStorage so they come back in
 * every new window.
 */

const URL_MAX_LENGTH = 2000;
const TITLE_MAX_LENGTH = 200;

/** Only backend pages of this server can be stored as tabs. */
export function isSafeTabUrl(url) {
    if (typeof url !== "string" || !url || url.length > URL_MAX_LENGTH) {
        return false;
    }
    if (!url.startsWith("/") || url.startsWith("//")) {
        return false;
    }
    const path = url.split(/[?#]/)[0];
    return path === "/odoo" || path.startsWith("/odoo/");
}

function sanitizeTab(tab) {
    if (!tab || typeof tab !== "object" || !isSafeTabUrl(tab.url)) {
        return null;
    }
    return {
        id: String(tab.id || ""),
        url: tab.url,
        title: String(tab.title || "").slice(0, TITLE_MAX_LENGTH),
        pinned: Boolean(tab.pinned),
    };
}

export class TabStore {
    /**
     * @param {{ maxTabs?: number, newId?: () => string }} [options]
     */
    constructor({ maxTabs = 10, newId } = {}) {
        this.maxTabs = maxTabs;
        this.tabs = [];
        this.activeId = null;
        let counter = 0;
        this.newId = newId || (() => `t${Date.now().toString(36)}${(counter++).toString(36)}`);
    }

    get activeTab() {
        return this.tabs.find((tab) => tab.id === this.activeId) || null;
    }

    getTab(id) {
        return this.tabs.find((tab) => tab.id === id) || null;
    }

    /** Restore tabs from untrusted storage data; invalid entries are dropped. */
    load(data) {
        const tabs = Array.isArray(data?.tabs) ? data.tabs.map(sanitizeTab).filter(Boolean) : [];
        const seen = new Set();
        this.tabs = tabs.filter((tab) => {
            if (!tab.id || seen.has(tab.id)) {
                tab.id = this.newId();
            }
            seen.add(tab.id);
            return true;
        });
        this.activeId = this.getTab(data?.activeId) ? data.activeId : this.tabs[0]?.id || null;
        this.enforceLimit();
    }

    toJSON() {
        return { tabs: this.tabs.map((tab) => ({ ...tab })), activeId: this.activeId };
    }

    /** Pinned tabs first, keeping their relative order. */
    sort() {
        this.tabs = [...this.tabs.filter((t) => t.pinned), ...this.tabs.filter((t) => !t.pinned)];
    }

    /**
     * Open a new tab after the active one and activate it.
     *
     * @returns {object|null} the new tab
     */
    open(url, title = "", { activate = true } = {}) {
        const tab = sanitizeTab({ id: this.newId(), url, title });
        if (!tab) {
            return null;
        }
        const index = this.tabs.findIndex((t) => t.id === this.activeId);
        this.tabs.splice(index === -1 ? this.tabs.length : index + 1, 0, tab);
        this.sort();
        if (activate || !this.activeId) {
            this.activeId = tab.id;
        }
        this.enforceLimit();
        return tab;
    }

    /** The page shown in the active tab changed. */
    updateActive(url, title) {
        if (!isSafeTabUrl(url)) {
            return false;
        }
        let tab = this.activeTab;
        if (!tab) {
            tab = this.open(url, title);
            return Boolean(tab);
        }
        const newTitle = String(title || "").slice(0, TITLE_MAX_LENGTH);
        if (tab.url === url && (!newTitle || tab.title === newTitle)) {
            return false;
        }
        tab.url = url;
        if (newTitle) {
            tab.title = newTitle;
        }
        return true;
    }

    activate(id) {
        if (!this.getTab(id)) {
            return null;
        }
        this.activeId = id;
        return this.activeTab;
    }

    /**
     * Close tabs. The last remaining tab is never closed.
     *
     * @param {string[]} ids
     * @returns {object|null} the tab to show if the active one was closed
     */
    close(ids) {
        const toClose = new Set(ids);
        if (toClose.size >= this.tabs.length) {
            // Keep one tab open: the active one if it is listed, else the first.
            const keep = this.activeTab || this.tabs[0];
            toClose.delete(keep?.id);
        }
        const activeIndex = this.tabs.findIndex((t) => t.id === this.activeId);
        const activeClosed = toClose.has(this.activeId);
        const remaining = this.tabs.filter((t) => !toClose.has(t.id));
        if (!remaining.length) {
            return null;
        }
        this.tabs = remaining;
        if (!activeClosed) {
            return null;
        }
        // Like browsers: activate the tab that took the closed one's place,
        // or the previous one when the last tab was closed.
        const next = remaining[Math.min(activeIndex, remaining.length - 1)];
        this.activeId = next.id;
        return next;
    }

    closeOthers(id) {
        return this.close(this.tabs.filter((t) => t.id !== id && !t.pinned).map((t) => t.id));
    }

    closeToTheRight(id) {
        const index = this.tabs.findIndex((t) => t.id === id);
        return this.close(this.tabs.slice(index + 1).filter((t) => !t.pinned).map((t) => t.id));
    }

    closeAll() {
        const unpinned = this.tabs.filter((t) => !t.pinned).map((t) => t.id);
        return this.close(unpinned);
    }

    duplicate(id) {
        const tab = this.getTab(id);
        if (!tab) {
            return null;
        }
        const previous = this.activeId;
        this.activeId = id;
        const copy = this.open(tab.url, tab.title);
        if (!copy) {
            this.activeId = previous;
        }
        return copy;
    }

    togglePin(id) {
        const tab = this.getTab(id);
        if (tab) {
            tab.pinned = !tab.pinned;
            this.sort();
        }
        return tab;
    }

    /** Move a tab to the position of another one (drag and drop). */
    move(id, targetId) {
        const from = this.tabs.findIndex((t) => t.id === id);
        const to = this.tabs.findIndex((t) => t.id === targetId);
        if (from === -1 || to === -1 || from === to) {
            return false;
        }
        const [tab] = this.tabs.splice(from, 1);
        tab.pinned = this.tabs[Math.min(to, this.tabs.length - 1)]?.pinned ?? tab.pinned;
        this.tabs.splice(to, 0, tab);
        this.sort();
        return true;
    }

    /** Drop the oldest unpinned, inactive tabs beyond the limit. */
    enforceLimit() {
        while (this.tabs.length > this.maxTabs) {
            const victim = this.tabs.find((t) => !t.pinned && t.id !== this.activeId);
            if (!victim) {
                break;
            }
            this.tabs = this.tabs.filter((t) => t !== victim);
        }
    }

    /** Pinned tabs, as saved for new windows. */
    pinnedTabs() {
        return this.tabs.filter((t) => t.pinned).map((t) => ({ ...t }));
    }

    /** Add saved pinned tabs that are not open yet (a new window). */
    mergePinned(pinned) {
        if (!Array.isArray(pinned)) {
            return;
        }
        for (const raw of pinned) {
            const tab = sanitizeTab({ ...raw, pinned: true });
            if (tab && !this.tabs.some((t) => t.pinned && t.url === tab.url)) {
                tab.id = this.newId();
                this.tabs.push(tab);
            }
        }
        this.sort();
        this.enforceLimit();
    }
}
