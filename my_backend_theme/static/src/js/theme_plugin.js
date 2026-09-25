import { computed, Plugin, signal, useEffect, useListener } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { cookie } from "@web/core/browser/cookie";
import { services } from "@web/core/services";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { applyRootState, isSidebarStyle, resolveConfig, THEME_MODES, UI_SCALES } from "./theme_config";

/** res.users.settings fields a user may change through the plugin. */
const USER_PREFERENCES = {
    mbt_ui_scale: (value) =>
        value === false || (typeof value === "string" && UI_SCALES.includes(Number(value))),
    mbt_reduce_motion: (value) => typeof value === "boolean",
    mbt_theme_mode: (value) => value === false || THEME_MODES.includes(value),
    mbt_sidebar_collapsed: (value) => typeof value === "boolean",
};

/** Mirrors DEVICE_SCHEME_COOKIE in models/ir_http.py. */
const DEVICE_SCHEME_COOKIE = "mbt_device_scheme";
/** Guards against reload loops when cookies cannot be stored. */
const RELOAD_GUARD_KEY = "mbt_scheme_reload";

export function logError(message, error) {
    console.error(`[my_backend_theme] ${message}`, error);
}

function isDarkBundleLoaded() {
    return Boolean(document.querySelector('link[href*="web.assets_web_dark"]'));
}

/**
 * Central state of the backend theme.
 *
 * Every theme feature reads the configuration from here (`usePlugin(ThemePlugin)`)
 * instead of fetching settings on its own. The resolved configuration is a
 * computed signal, so components reading it re-render when it changes.
 *
 * Failures are contained: if anything goes wrong the plugin logs it and the
 * backend keeps Odoo's default appearance.
 */
export class ThemePlugin extends Plugin {
    /** Company-wide settings, sent by the server in the session info. */
    globalConfig = signal(session.backend_theme || {});
    /** The current user's own preferences (res.users.settings). */
    userSettings = signal(user.settings);
    /** Whether the device asks for a dark color scheme. */
    deviceDark = signal(browser.matchMedia?.("(prefers-color-scheme: dark)").matches || false);
    /** Color scheme of the stylesheet the server sent. */
    loadedScheme = isDarkBundleLoaded() ? "dark" : "light";

    config = computed(() => resolveConfig(this.globalConfig(), this.userSettings()));

    /** The color scheme the user should see: "light" or "dark". */
    colorScheme = computed(() => {
        const mode = this.config().theme_mode;
        if (mode === "system") {
            return this.deviceDark() ? "dark" : "light";
        }
        return mode;
    });

    hasSidebar = computed(() => isSidebarStyle(this.config().menu_style));

    setup() {
        const darkQuery = browser.matchMedia?.("(prefers-color-scheme: dark)");
        if (darkQuery) {
            useListener(darkQuery, "change", (ev) => this.deviceDark.set(ev.matches));
        }
        useEffect(() => {
            const config = this.config();
            try {
                applyRootState(document.documentElement, config, {
                    "data-mbt-color-scheme": this.loadedScheme,
                });
            } catch (error) {
                logError("Could not apply the theme.", error);
            }
        });
        useEffect(() => {
            const scheme = this.colorScheme();
            try {
                this.syncColorScheme(scheme);
            } catch (error) {
                logError("Could not switch the color scheme.", error);
            }
        });
    }

    /**
     * The color scheme is a separate stylesheet chosen by the server, so a
     * change needs a reload. The device's scheme is stored in a cookie for the
     * server to read when the user follows their device.
     *
     * @param {"light"|"dark"} scheme
     */
    syncColorScheme(scheme) {
        if (cookie.get(DEVICE_SCHEME_COOKIE) !== (this.deviceDark() ? "dark" : "light")) {
            cookie.set(DEVICE_SCHEME_COOKIE, this.deviceDark() ? "dark" : "light");
        }
        if (scheme === this.loadedScheme || !this.config().enable_dark_mode) {
            browser.sessionStorage.removeItem(RELOAD_GUARD_KEY);
            return;
        }
        // Reload at most once per requested scheme, in case the server keeps
        // answering with the other stylesheet (e.g. cookies are blocked).
        if (browser.sessionStorage.getItem(RELOAD_GUARD_KEY) === scheme) {
            return;
        }
        browser.sessionStorage.setItem(RELOAD_GUARD_KEY, scheme);
        browser.location.reload();
    }

    /**
     * @param {keyof import("./theme_config").DEFAULT_CONFIG} key
     */
    get(key) {
        return this.config()[key];
    }

    /**
     * Save one of the current user's theme preferences and apply it at once.
     *
     * @param {keyof USER_PREFERENCES} key
     * @param {*} value
     * @returns {Promise<boolean>} whether the preference was saved
     */
    async setUserPreference(key, value) {
        if (!USER_PREFERENCES[key]?.(value)) {
            logError(`Rejected invalid preference ${key}.`, value);
            return false;
        }
        try {
            await user.setUserSettings(key, value);
        } catch (error) {
            logError(`Could not save preference ${key}.`, error);
            return false;
        }
        this.userSettings.set(user.settings);
        return true;
    }

    /** Switch between light and dark, leaving "follow the device" if set. */
    toggleDarkMode() {
        return this.setUserPreference(
            "mbt_theme_mode",
            this.colorScheme() === "dark" ? "light" : "dark"
        );
    }
}

services.add(ThemePlugin);
