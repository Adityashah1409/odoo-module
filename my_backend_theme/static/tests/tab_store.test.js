import { describe, expect, test } from "@odoo/hoot";
import { isSafeTabUrl, TabStore } from "@my_backend_theme/tabs/tab_store";

describe.current.tags("headless");

function makeStore(maxTabs = 10) {
    let id = 0;
    return new TabStore({ maxTabs, newId: () => `t${++id}` });
}

function urls(store) {
    return store.tabs.map((tab) => tab.url);
}

test("only backend URLs of this server are accepted", () => {
    expect(isSafeTabUrl("/odoo")).toBe(true);
    expect(isSafeTabUrl("/odoo/contacts/4?debug=1")).toBe(true);
    expect(isSafeTabUrl("//evil.example/odoo")).toBe(false);
    expect(isSafeTabUrl("https://evil.example/odoo")).toBe(false);
    expect(isSafeTabUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeTabUrl("/web/login")).toBe(false);
    expect(isSafeTabUrl("/odoofake")).toBe(false);
    expect(isSafeTabUrl(42)).toBe(false);
});

test("open inserts after the active tab and activates it", () => {
    const store = makeStore();
    store.open("/odoo/a", "A");
    store.open("/odoo/b", "B");
    store.activate("t1");
    store.open("/odoo/c", "C");
    expect(urls(store)).toEqual(["/odoo/a", "/odoo/c", "/odoo/b"]);
    expect(store.activeTab.url).toBe("/odoo/c");
    expect(store.open("https://evil.example/odoo")).toBe(null);
});

test("the active tab follows navigation", () => {
    const store = makeStore();
    expect(store.updateActive("/odoo/a", "A")).toBe(true);
    expect(store.tabs).toHaveLength(1);
    expect(store.updateActive("/odoo/a", "A")).toBe(false);
    expect(store.updateActive("/odoo/b", "")).toBe(true);
    expect(store.activeTab).toEqual({ id: "t1", url: "/odoo/b", title: "A", pinned: false });
    expect(store.updateActive("//evil.example/odoo", "X")).toBe(false);
});

test("closing the active tab activates its neighbour", () => {
    const store = makeStore();
    for (const name of ["a", "b", "c"]) {
        store.open(`/odoo/${name}`, name);
    }
    store.activate("t2");
    expect(store.close(["t2"]).id).toBe("t3");
    store.activate("t3");
    expect(store.close(["t3"]).id).toBe("t1");
    // The last tab is never closed.
    expect(store.close(["t1"])).toBe(null);
    expect(urls(store)).toEqual(["/odoo/a"]);
});

test("close others, to the right and all keep pinned tabs", () => {
    const store = makeStore();
    for (const name of ["a", "b", "c", "d"]) {
        store.open(`/odoo/${name}`, name);
    }
    store.togglePin("t4");
    expect(urls(store)).toEqual(["/odoo/d", "/odoo/a", "/odoo/b", "/odoo/c"]);
    store.closeToTheRight("t1");
    expect(urls(store)).toEqual(["/odoo/d", "/odoo/a"]);
    store.open("/odoo/e", "e");
    store.closeOthers("t5");
    expect(urls(store)).toEqual(["/odoo/d", "/odoo/e"]);
    store.closeAll();
    expect(urls(store)).toEqual(["/odoo/d"]);
    expect(store.activeTab.url).toBe("/odoo/d");
});

test("the limit drops the oldest unpinned inactive tab", () => {
    const store = makeStore(3);
    store.open("/odoo/a", "a");
    store.togglePin("t1");
    store.open("/odoo/b", "b");
    store.open("/odoo/c", "c");
    store.open("/odoo/d", "d");
    expect(urls(store)).toEqual(["/odoo/a", "/odoo/c", "/odoo/d"]);
});

test("duplicate and move", () => {
    const store = makeStore();
    store.open("/odoo/a", "a");
    store.open("/odoo/b", "b");
    const copy = store.duplicate("t1");
    expect(copy.url).toBe("/odoo/a");
    expect(store.activeId).toBe(copy.id);
    expect(urls(store)).toEqual(["/odoo/a", "/odoo/a", "/odoo/b"]);
    expect(store.move("t2", "t1")).toBe(true);
    expect(store.tabs[0].id).toBe("t2");
});

test("untrusted saved data is sanitised", () => {
    const store = makeStore();
    store.load({
        tabs: [
            { id: "x", url: "/odoo/a", title: "A" },
            { id: "x", url: "/odoo/b", title: "B" },
            { id: "y", url: "javascript:alert(1)", title: "Bad" },
            "garbage",
        ],
        activeId: "nope",
    });
    expect(urls(store)).toEqual(["/odoo/a", "/odoo/b"]);
    expect(new Set(store.tabs.map((t) => t.id)).size).toBe(2);
    expect(store.activeId).toBe("x");
    store.load(null);
    expect(store.tabs).toEqual([]);
});

test("pinned tabs are restored once in new windows", () => {
    const store = makeStore();
    store.open("/odoo/a", "a");
    store.mergePinned([{ url: "/odoo/p", title: "P" }, { url: "https://evil.example" }]);
    store.mergePinned([{ url: "/odoo/p", title: "P" }]);
    expect(urls(store)).toEqual(["/odoo/p", "/odoo/a"]);
    expect(store.pinnedTabs()).toHaveLength(1);
});
