/**
 * Pure helpers turning the theme configuration into DOM state.
 *
 * Kept free of Odoo services so they can be unit tested and reused by every
 * theme component. Nothing here trusts its input: values that fail validation
 * fall back to defaults, so a bad configuration can only ever produce Odoo's
 * standard look, never arbitrary CSS.
 */

const COLOR_RE = /^#[0-9a-f]{6}$/i;

export const UI_SCALES = [90, 100, 110, 120];

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

export const DEFAULT_CONFIG = Object.freeze({
    primary_color: false,
    navbar_color: false,
    ui_scale: 100,
    font_family: "system",
    reduce_motion: false,
});

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
    "--mbt-ui-scale",
    "--mbt-font-family",
];

export function sanitizeColor(value) {
    return typeof value === "string" && COLOR_RE.test(value) ? value.toLowerCase() : false;
}

function sanitizeScale(value) {
    const scale = Number(value);
    return UI_SCALES.includes(scale) ? scale : null;
}

/**
 * Merge the global configuration with the current user's preferences.
 *
 * @param {Object} [globalConfig] company-wide settings from the session
 * @param {Object} [userSettings] the user's res.users.settings values
 * @returns {typeof DEFAULT_CONFIG}
 */
export function resolveConfig(globalConfig = {}, userSettings = {}) {
    const fontFamily = Object.hasOwn(FONT_STACKS, globalConfig.font_family)
        ? globalConfig.font_family
        : DEFAULT_CONFIG.font_family;
    return {
        primary_color: sanitizeColor(globalConfig.primary_color),
        navbar_color: sanitizeColor(globalConfig.navbar_color),
        ui_scale:
            sanitizeScale(userSettings.mbt_ui_scale) ??
            sanitizeScale(globalConfig.ui_scale) ??
            DEFAULT_CONFIG.ui_scale,
        font_family: fontFamily,
        reduce_motion: Boolean(globalConfig.reduce_motion || userSettings.mbt_reduce_motion),
    };
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
        variables["--mbt-navbar-hover-bg"] = `color-mix(in srgb, ${foreground} 12%, transparent)`;
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
    if (config.reduce_motion) {
        attributes["data-mbt-reduce-motion"] = "";
    }
    return { attributes, variables };
}

/**
 * Reflect the configuration on `root`, removing whatever a previous call set
 * and is no longer needed.
 *
 * @param {HTMLElement} root
 * @param {typeof DEFAULT_CONFIG} config
 */
export function applyRootState(root, config) {
    const { attributes, variables } = computeRootState(config);
    for (const name of root.getAttributeNames()) {
        if (name.startsWith("data-mbt-") && !(name in attributes)) {
            root.removeAttribute(name);
        }
    }
    for (const [name, value] of Object.entries(attributes)) {
        root.setAttribute(name, value);
    }
    for (const name of CSS_VARIABLES) {
        if (name in variables) {
            root.style.setProperty(name, variables[name]);
        } else {
            root.style.removeProperty(name);
        }
    }
}
