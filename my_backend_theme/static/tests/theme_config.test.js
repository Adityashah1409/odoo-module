import { describe, expect, test } from "@odoo/hoot";
import {
    applyRootState,
    computeRootState,
    contrastColor,
    DEFAULT_CONFIG,
    resolveConfig,
    sanitizeHotkey,
} from "@my_backend_theme/js/theme_config";

describe.current.tags("headless");

test("defaults when nothing is configured", () => {
    expect(resolveConfig()).toEqual({ ...DEFAULT_CONFIG });
    expect(computeRootState(resolveConfig())).toEqual({ attributes: {}, variables: {} });
});

test("invalid values never reach the page", () => {
    const config = resolveConfig({
        primary_color: "red; background: url(x)",
        navbar_color: "#12345",
        font_family: "evil",
        sidebar_width: 5000,
        ui_scale: "300",
        menu_style: 42,
        shortcut_search: "shift+f",
        shortcut_bookmarks: false,
    });
    expect(config.primary_color).toBe(false);
    expect(config.navbar_color).toBe(false);
    expect(config.font_family).toBe("system");
    expect(config.sidebar_width).toBe(240);
    expect(config.ui_scale).toBe(100);
    expect(config.menu_style).toBe("horizontal");
    expect(config.shortcut_search).toBe(false);
    expect(config.shortcut_bookmarks).toBe(false);
    expect(config.shortcut_recent).toBe("alt+shift+r");
});

test("user preferences override the company settings", () => {
    const config = resolveConfig(
        { ui_scale: "110", default_theme_mode: "dark" },
        { mbt_ui_scale: "90", mbt_theme_mode: "system", mbt_sidebar_collapsed: true }
    );
    expect(config.ui_scale).toBe(90);
    expect(config.theme_mode).toBe("system");
    expect(config.sidebar_collapsed).toBe(true);
    expect(resolveConfig({ enable_dark_mode: false }, { mbt_theme_mode: "dark" }).theme_mode).toBe(
        "light"
    );
});

test("colors become variables with a readable text color", () => {
    const { attributes, variables } = computeRootState(
        resolveConfig({ primary_color: "#1D6FB8", navbar_color: "#ffffff", menu_style: "sidebar" })
    );
    expect(variables["--mbt-primary"]).toBe("#1d6fb8");
    expect(variables["--mbt-primary-rgb"]).toBe("29, 111, 184");
    expect(variables["--mbt-navbar-fg"]).toBe("#1f2937");
    expect(variables["--mbt-sidebar-width"]).toBe("240px");
    expect(attributes["data-mbt-menu-style"]).toBe("sidebar");
    expect(contrastColor("#000000")).toBe("#ffffff");
});

test("hotkeys follow Odoo's syntax", () => {
    expect(sanitizeHotkey("alt+shift+q")).toBe("alt+shift+q");
    expect(sanitizeHotkey("alt+control+k")).toBe("alt+control+k");
    expect(sanitizeHotkey("control+alt+k")).toBe(false);
    expect(sanitizeHotkey("shift+k")).toBe(false);
    expect(sanitizeHotkey("alt+f5")).toBe(false);
});

test("applyRootState cleans up after itself but keeps component flags", () => {
    const root = document.createElement("div");
    root.setAttribute("data-mbt-sidebar-mounted", "");
    applyRootState(root, resolveConfig({ list_striped: true, primary_color: "#112233" }));
    expect(root.hasAttribute("data-mbt-list-striped")).toBe(true);
    expect(root.style.getPropertyValue("--mbt-primary")).toBe("#112233");
    applyRootState(root, resolveConfig());
    expect(root.hasAttribute("data-mbt-list-striped")).toBe(false);
    expect(root.style.getPropertyValue("--mbt-primary")).toBe("");
    expect(root.hasAttribute("data-mbt-sidebar-mounted")).toBe(true);
});
