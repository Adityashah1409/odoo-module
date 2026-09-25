import { computed, Plugin, signal, useEffect } from "@odoo/owl";
import { services } from "@web/core/services";
import { user } from "@web/core/user";
import { session } from "@web/session";
import { applyRootState, resolveConfig, UI_SCALES } from "./theme_config";

/** res.users.settings fields a user may change through the plugin. */
const USER_PREFERENCES = {
    mbt_ui_scale: (value) =>
        value === false || (typeof value === "string" && UI_SCALES.includes(Number(value))),
    mbt_reduce_motion: (value) => typeof value === "boolean",
};

function logError(message, error) {
    console.error(`[my_backend_theme] ${message}`, error);
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

    config = computed(() => resolveConfig(this.globalConfig(), this.userSettings()));

    setup() {
        useEffect(() => {
            const config = this.config();
            try {
                applyRootState(document.documentElement, config);
            } catch (error) {
                logError("Could not apply the theme.", error);
            }
        });
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
}

services.add(ThemePlugin);
