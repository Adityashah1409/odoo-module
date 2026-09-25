/**
 * Pure helpers turning the theme configuration into DOM state.
 *
 * Kept free of Odoo services so they can be unit tested and reused by every
 * theme component. The server already validates the configuration; values
 * that end up in CSS (colors, sizes) are validated once more here, so a bad
 * value can only ever produce Odoo's standard look, never arbitrary CSS.
 */

const COLOR_RE = /^#[0-9a-f]{6}$/i;

export const UI_SCALES = [90, 100, 110, 120];
export const THEME_MODES = ["light", "dark", "system"];

const SANS_FALLBACK =
    'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';

/** Font stacks by setting value. `system` keeps Odoo's own stack. */
export const FONT_STACKS = {
    system: null,
    inter: `"Inter", ${SANS_FALLBACK}`,
    roboto: `"Roboto", ${SANS_FALLBACK}`,
    open_sans: `"Open Sans", ${SANS_FALLBACK}`,
    poppins: `"Poppins", ${SANS_FALLBACK}`,
};

export const SIDEBAR_STYLES = ["sidebar", "compact", "icons"];

export const DEFAULT_CONFIG = Object.freeze({
    primary_color: false,
    navbar_color: false,
    sidebar_color: false,
    accent_color: false,
    ui_scale: 100,
    font_family: "system",
    reduce_motion: false,
    enable_dark_mode: true,
    default_theme_mode: "light",
    theme_mode: "light",
    menu_style: "horizontal",
    sidebar_width: 240,
    sidebar_hover_expand: true,
    sidebar_collapsed: false,
    icon_style: "default",
    compact_navbar: false,
    list_density: "default",
    list_striped: false,
    list_borderless: false,
    form_style: "default",
    form_sticky_statusbar: true,
    chatter_position: "auto",
    button_style: "default",
    checkbox_style: "default",
    scrollbar_style: "default",
    rounded_fields: false,
    enable_quick_create: true,
    enable_bookmarks: true,
    enable_recent: true,
    recent_limit: 20,
    enable_tabs: false,
    max_tabs: 10,
    enable_split_view: true,
    enable_global_search: true,
    search_limit: 5,
    shortcut_quick_create: "alt+shift+n",
    shortcut_bookmarks: "alt+shift+b",
    shortcut_recent: "alt+shift+r",
    shortcut_search: "alt+shift+f",
    shortcut_dark_mode: "alt+shift+d",
    shortcut_new_tab: "alt+shift+t",
});

/** Mirrors HOTKEY_PATTERN in models/theme_config.py. */
const HOTKEY_RE = /^(alt\+)?(control\+)?(shift\+)?[a-z0-9]$/;
const SHORTCUT_KEYS = Object.keys(DEFAULT_CONFIG).filter((key) => key.startsWith("shortcut_"));

export function sanitizeHotkey(value) {
    return typeof value === "string" && HOTKEY_RE.test(value) && /^(alt|control)\+/.test(value)
        ? value
        : false;
}

/**
 * Settings reflected as `data-mbt-<name>` attributes on <html> when they
 * differ from their default. Attribute values are never interpreted as CSS,
 * so enumerated values can be passed through as they are.
 */
const ATTRIBUTE_SETTINGS = [
    "menu_style",
    "icon_style",
    "list_density",
    "form_style",
    "chatter_position",
    "button_style",
    "checkbox_style",
    "scrollbar_style",
];
const FLAG_SETTINGS = [
    "compact_navbar",
    "list_striped",
    "list_borderless",
    "rounded_fields",
    "reduce_motion",
];

/** Names of the CSS custom properties this module may set on the root. */
const CSS_VARIABLES = [
    "--mbt-primary",
    "--mbt-primary-rgb",
    "--mbt-primary-hover",
    "--mbt-primary-active",
    "--mbt-primary-contrast",
    "--mbt-navbar-bg",
    "--mbt-navbar-fg",
    "--mbt-navbar-hover-bg",
    "--mbt-sidebar-bg",
    "--mbt-sidebar-fg",
    "--mbt-sidebar-hover-bg",
    "--mbt-accent",
    "--mbt-accent-fg",
    "--mbt-sidebar-width",
    "--mbt-ui-scale",
    "--mbt-font-family",
];

export function sanitizeColor(value) {
    return typeof value === "string" && COLOR_RE.test(value) ? value.toLowerCase() : false;
}

function sanitizeScale(value) {
    const scale = Number(value);
    return value && UI_SCALES.includes(scale) ? scale : null;
}

function sanitizeWidth(value) {
    const width = Number(value);
    return Number.isInteger(width) && width >= 180 && width <= 360
        ? width
        : DEFAULT_CONFIG.sidebar_width;
}

/**
 * Merge the global configuration with the current user's preferences.
 *
 * @param {Object} [globalConfig] company-wide settings from the session
 * @param {Object} [userSettings] the user's res.users.settings values
 * @returns {typeof DEFAULT_CONFIG}
 */
export function resolveConfig(globalConfig = {}, userSettings = {}) {
    const config = { ...DEFAULT_CONFIG };
    for (const key in DEFAULT_CONFIG) {
        if (key in globalConfig && typeof globalConfig[key] === typeof DEFAULT_CONFIG[key]) {
            config[key] = globalConfig[key];
        }
    }
    for (const key of ["primary_color", "navbar_color", "sidebar_color", "accent_color"]) {
        config[key] = sanitizeColor(globalConfig[key]);
    }
    config.font_family = Object.hasOwn(FONT_STACKS, globalConfig.font_family)
        ? globalConfig.font_family
        : DEFAULT_CONFIG.font_family;
    config.sidebar_width = sanitizeWidth(globalConfig.sidebar_width);
    for (const key of SHORTCUT_KEYS) {
        // false means the shortcut was turned off.
        config[key] =
            key in globalConfig ? sanitizeHotkey(globalConfig[key]) : DEFAULT_CONFIG[key];
    }
    config.ui_scale =
        sanitizeScale(userSettings.mbt_ui_scale) ??
        sanitizeScale(globalConfig.ui_scale) ??
        DEFAULT_CONFIG.ui_scale;
    config.reduce_motion = Boolean(globalConfig.reduce_motion || userSettings.mbt_reduce_motion);
    config.sidebar_collapsed = Boolean(userSettings.mbt_sidebar_collapsed);
    if (!config.enable_dark_mode) {
        config.theme_mode = "light";
    } else if (THEME_MODES.includes(userSettings.mbt_theme_mode)) {
        config.theme_mode = userSettings.mbt_theme_mode;
    } else if (THEME_MODES.includes(config.default_theme_mode)) {
        config.theme_mode = config.default_theme_mode;
    }
    return config;
}

export function isSidebarStyle(menuStyle) {
    return SIDEBAR_STYLES.includes(menuStyle);
}

function hexToRgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** WCAG relative luminance of a `#rrggbb` color. */
function luminance(hex) {
    const [r, g, b] = hexToRgb(hex).map((c) => {
        const s = c / 255;
        return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Text color with the better contrast on the given background. */
export function contrastColor(hex) {
    // 0.179 is where white and near-black text have equal contrast ratios.
    return luminance(hex) > 0.179 ? "#1f2937" : "#ffffff";
}

function shade(hex, percent) {
    return `color-mix(in srgb, ${hex} ${100 - percent}%, #000000)`;
}

function translucent(color, percent) {
    return `color-mix(in srgb, ${color} ${percent}%, transparent)`;
}

/**
 * Compute the attributes and CSS variables to put on the root element.
 *
 * @param {typeof DEFAULT_CONFIG} config a resolved configuration
 * @returns {{ attributes: Object<string, string>, variables: Object<string, string> }}
 */
export function computeRootState(config) {
    const attributes = {};
    const variables = {};
    if (config.primary_color) {
        const color = config.primary_color;
        attributes["data-mbt-primary"] = "";
        variables["--mbt-primary"] = color;
        variables["--mbt-primary-rgb"] = hexToRgb(color).join(", ");
        variables["--mbt-primary-hover"] = shade(color, 12);
        variables["--mbt-primary-active"] = shade(color, 20);
        variables["--mbt-primary-contrast"] = contrastColor(color);
    }
    if (config.navbar_color) {
        const color = config.navbar_color;
        const foreground = contrastColor(color);
        attributes["data-mbt-navbar"] = "";
        variables["--mbt-navbar-bg"] = color;
        variables["--mbt-navbar-fg"] = foreground;
        variables["--mbt-navbar-hover-bg"] = translucent(foreground, 12);
    }
    if (config.sidebar_color) {
        const color = config.sidebar_color;
        const foreground = contrastColor(color);
        attributes["data-mbt-sidebar-color"] = "";
        variables["--mbt-sidebar-bg"] = color;
        variables["--mbt-sidebar-fg"] = foreground;
        variables["--mbt-sidebar-hover-bg"] = translucent(foreground, 10);
    }
    if (config.accent_color) {
        attributes["data-mbt-accent"] = "";
        variables["--mbt-accent"] = config.accent_color;
        variables["--mbt-accent-fg"] = contrastColor(config.accent_color);
    }
    if (config.ui_scale !== DEFAULT_CONFIG.ui_scale) {
        attributes["data-mbt-ui-scale"] = String(config.ui_scale);
        variables["--mbt-ui-scale"] = String(config.ui_scale / 100);
    }
    const fontStack = FONT_STACKS[config.font_family];
    if (fontStack) {
        attributes["data-mbt-font"] = config.font_family;
        variables["--mbt-font-family"] = fontStack;
    }
    for (const key of ATTRIBUTE_SETTINGS) {
        if (config[key] !== DEFAULT_CONFIG[key]) {
            attributes[`data-mbt-${key.replaceAll("_", "-")}`] = String(config[key]);
        }
    }
    for (const key of FLAG_SETTINGS) {
        if (config[key]) {
            attributes[`data-mbt-${key.replaceAll("_", "-")}`] = "";
        }
    }
    // Odoo's status bar is sticky by default: only its opt-out is flagged.
    if (!config.form_sticky_statusbar) {
        attributes["data-mbt-static-statusbar"] = "";
    }
    if (isSidebarStyle(config.menu_style)) {
        variables["--mbt-sidebar-width"] = `${config.sidebar_width}px`;
        if (config.menu_style === "sidebar" && config.sidebar_collapsed) {
            attributes["data-mbt-sidebar-collapsed"] = "";
        }
        if (config.sidebar_hover_expand) {
            attributes["data-mbt-sidebar-hover-expand"] = "";
        }
    }
    return { attributes, variables };
}

/**
 * Reflect the configuration on `root`, removing whatever a previous call set
 * and is no longer needed.
 *
 * @param {HTMLElement} root
 * @param {typeof DEFAULT_CONFIG} config
 * @param {Object<string, string>} [extraAttributes] attributes managed elsewhere
 */
export function applyRootState(root, config, extraAttributes = {}) {
    const { attributes, variables } = computeRootState(config);
    Object.assign(attributes, extraAttributes);
    for (const name of root.getAttributeNames()) {
        if (name.startsWith("data-mbt-") && !(name in attributes)) {
            root.removeAttribute(name);
        }
    }
    for (const [name, value] of Object.entries(attributes)) {
        if (root.getAttribute(name) !== value) {
            root.setAttribute(name, value);
        }
    }
    for (const name of CSS_VARIABLES) {
        if (name in variables) {
            root.style.setProperty(name, variables[name]);
        } else {
            root.style.removeProperty(name);
        }
    }
}
