import { usePlugin } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { ThemePlugin } from "./theme_plugin";

export const THEME_SETTINGS_ACTION = {
    type: "ir.actions.act_window",
    name: _t("Backend Theme"),
    res_model: "res.config.settings",
    views: [[false, "form"]],
    target: "inline",
    context: { module: "my_backend_theme" },
};

function darkModeItem() {
    const theme = usePlugin(ThemePlugin);
    return {
        type: "switch",
        id: "mbt_dark_mode",
        description: _t("Dark Mode"),
        hide: !theme.get("enable_dark_mode"),
        isChecked: theme.colorScheme() === "dark",
        callback: () => theme.toggleDarkMode(),
        sequence: 45,
    };
}

function highContrastItem() {
    const theme = usePlugin(ThemePlugin);
    return {
        type: "switch",
        id: "mbt_high_contrast",
        description: _t("High Contrast"),
        // Turned on for everyone by an administrator: nothing to switch.
        hide: Boolean(theme.globalConfig().high_contrast),
        isChecked: theme.get("high_contrast"),
        callback: () => theme.toggleHighContrast(),
        sequence: 46,
    };
}

function themeSettingsItem() {
    const action = useService("action");
    return {
        type: "item",
        id: "mbt_theme_settings",
        description: _t("Theme Settings"),
        hide: !user.isSystem,
        callback: () => action.doAction(THEME_SETTINGS_ACTION),
        sequence: 55,
    };
}

registry
    .category("user_menuitems")
    .add("mbt_dark_mode", darkModeItem)
    .add("mbt_high_contrast", highContrastItem)
    .add("mbt_theme_settings", themeSettingsItem);
