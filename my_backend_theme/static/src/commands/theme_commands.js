import { Component, t, usePlugin, useProps, xml } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { defaultCommandItemProps } from "@web/core/commands/command_palette";
import { ORM } from "@web/core/orm_plugin";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { THEME_SETTINGS_ACTION } from "../js/user_menu_items";
import { logError, startupConfig, ThemePlugin } from "../js/theme_plugin";
import { navigateTo, NavigationPlugin, recordUrl } from "../navigation/navigation_plugin";
import { useThemeHotkey } from "../navigation/systray_menus";
import { SPLIT_VIEW_TAG } from "../split_view/split_view";

export const SEARCH_NAMESPACE = "?";
const SEARCH_MODEL = "my.theme.search.model";
const MIN_QUERY_LENGTH = 2;

/** Palette row with an icon, an optional detail and a shortcut hint. */
export class ThemeCommandItem extends Component {
    static template = xml`
        <div class="o_command_default o_mbt_command d-flex align-items-center gap-2 px-4 py-2 cursor-pointer">
            <i t-if="this.props.icon" class="oi o_mbt_command_icon" t-att-data-icon="this.props.icon" aria-hidden="true"/>
            <t t-call-slot="name"/>
            <small t-if="this.props.detail" class="o_mbt_command_detail text-muted text-truncate" t-out="this.props.detail"/>
            <span class="ms-auto flex-shrink-0 d-flex align-items-center gap-2">
                <kbd t-if="this.props.shortcut" class="o_mbt_command_shortcut small" t-out="this.props.shortcut"/>
                <t t-call-slot="focusMessage"/>
            </span>
        </div>`;
    props = useProps({
        ...defaultCommandItemProps,
        icon: t.string().optional(),
        detail: t.string().optional(),
        shortcut: t.string().optional(),
    });
}

function shortcutLabel(hotkey) {
    return hotkey ? hotkey.split("+").map((key) => key.toUpperCase()).join(" + ") : "";
}

const commandCategoryRegistry = registry.category("command_categories");
commandCategoryRegistry.add("my_backend_theme", { name: _t("Theme") }, { sequence: 90 });

const commandSetupRegistry = registry.category("command_setup");
commandSetupRegistry.add(SEARCH_NAMESPACE, {
    debounceDelay: 300,
    emptyMessage: _t("No record found. Type at least 2 characters."),
    name: _t("records"),
    placeholder: _t("Search records in every app..."),
});

const commandProviderRegistry = registry.category("command_provider");

/** Global record search: `?` followed by a name, a reference... */
commandProviderRegistry.add("my_backend_theme.record_search", {
    namespace: SEARCH_NAMESPACE,
    async provide({ searchValue }) {
        const theme = usePlugin(ThemePlugin);
        const orm = usePlugin(ORM);
        const action = useService("action");
        const query = (searchValue || "").trim();
        if (!theme.get("enable_global_search") || query.length < MIN_QUERY_LENGTH) {
            return [];
        }
        let groups = [];
        try {
            groups = await orm.silent.call(SEARCH_MODEL, "global_search", [query]);
        } catch (error) {
            logError("Global search failed.", error);
            return [];
        }
        const commands = [];
        for (const group of groups) {
            for (const record of group.records) {
                commands.push({
                    Component: ThemeCommandItem,
                    name: record.name || _t("Unnamed"),
                    href: recordUrl(group.model, record.id),
                    props: { icon: "description", detail: group.label },
                    action() {
                        action.doAction({
                            type: "ir.actions.act_window",
                            res_model: group.model,
                            res_id: record.id,
                            views: [[false, "form"]],
                        });
                    },
                });
            }
        }
        return commands;
    },
});

/** Theme commands in the default palette (Ctrl+K). */
commandProviderRegistry.add("my_backend_theme.commands", {
    async provide() {
        const theme = usePlugin(ThemePlugin);
        const navigation = usePlugin(NavigationPlugin);
        const action = useService("action");
        const command = (name, run, props = {}, extra = {}) => ({
            Component: ThemeCommandItem,
            category: "my_backend_theme",
            name,
            action: run,
            props,
            ...extra,
        });
        const commands = [];

        if (theme.get("enable_global_search")) {
            commands.push(
                command(
                    _t("Search records"),
                    () => ({ searchValue: SEARCH_NAMESPACE }),
                    { icon: "search", shortcut: shortcutLabel(theme.get("shortcut_search")) }
                )
            );
        }
        if (theme.get("enable_dark_mode")) {
            const dark = theme.colorScheme() === "dark";
            commands.push(
                command(
                    dark ? _t("Switch to light mode") : _t("Switch to dark mode"),
                    () => theme.toggleDarkMode(),
                    {
                        icon: dark ? "light_mode" : "dark_mode",
                        shortcut: shortcutLabel(theme.get("shortcut_dark_mode")),
                    }
                )
            );
        }

        const page = navigation.getCurrentPage();
        commands.push(
            command(_t("Open this page in a new browser tab"), () => {
                browser.open(page.url, "_blank", "noopener");
            }, { icon: "open_in_new" })
        );

        const controller = action.currentController;
        const viewType = controller?.props?.type;
        if (
            theme.get("enable_split_view") &&
            ["list", "kanban"].includes(viewType) &&
            controller.props.resModel &&
            controller.action?.type === "ir.actions.act_window"
        ) {
            commands.push(
                command(_t("Open in split view"), () => {
                    action.doAction({
                        type: "ir.actions.client",
                        tag: SPLIT_VIEW_TAG,
                        name: controller.displayName || _t("Split View"),
                        params: {
                            split_model: controller.props.resModel,
                            split_action: Number.isInteger(controller.action.id)
                                ? controller.action.id
                                : false,
                        },
                    });
                }, { icon: "dock_to_right" })
            );
        }

        if (theme.get("enable_bookmarks")) {
            try {
                await navigation.loadBookmarks();
            } catch (error) {
                logError("Could not load bookmarks.", error);
            }
            const bookmarked = navigation.isBookmarked(page.url);
            commands.push(
                command(
                    bookmarked ? _t("Remove this page from bookmarks") : _t("Bookmark this page"),
                    () => navigation.toggleCurrentBookmark(),
                    { icon: bookmarked ? "bookmark_f" : "bookmark" }
                )
            );
            for (const bookmark of navigation.bookmarks() || []) {
                commands.push(
                    command(
                        bookmark.name,
                        () => navigateTo(bookmark.url),
                        { icon: "bookmark_f", detail: _t("Bookmark") },
                        { href: bookmark.url }
                    )
                );
            }
        }

        if (theme.get("enable_quick_create")) {
            try {
                await navigation.loadQuickCreateItems();
            } catch (error) {
                logError("Could not load quick create entries.", error);
            }
            for (const item of navigation.quickCreateItems() || []) {
                commands.push(
                    command(
                        _t("Create: %(name)s", { name: item.name }),
                        () => navigation.openQuickCreate(item),
                        { icon: item.icon || "add" }
                    )
                );
            }
        }

        if (theme.get("enable_recent")) {
            try {
                await navigation.loadRecent();
            } catch (error) {
                logError("Could not load recent records.", error);
            }
            for (const entry of (navigation.recent() || []).slice(0, 10)) {
                commands.push(
                    command(
                        entry.name,
                        () => navigation.openRecord(entry.res_model, entry.res_id),
                        { icon: "history", detail: entry.model_name },
                        { href: recordUrl(entry.res_model, entry.res_id) }
                    )
                );
            }
        }

        if (user.isSystem) {
            commands.push(
                command(_t("Theme settings"), () => action.doAction(THEME_SETTINGS_ACTION), {
                    icon: "palette",
                })
            );
        }
        return commands;
    },
});

/**
 * Global shortcuts that are not tied to a visible component: record search
 * and dark mode.
 */
export class ThemeShortcuts extends Component {
    static template = xml`<t/>`;

    setup() {
        const theme = usePlugin(ThemePlugin);
        const commandService = useService("command");
        const config = startupConfig();
        if (config.enable_global_search) {
            useThemeHotkey(config.shortcut_search, () =>
                commandService.openMainPalette({ searchValue: SEARCH_NAMESPACE })
            );
        }
        if (config.enable_dark_mode) {
            useThemeHotkey(config.shortcut_dark_mode, () => theme.toggleDarkMode());
        }
    }
}

registry.category("main_components").add("my_backend_theme.ThemeShortcuts", {
    Component: ThemeShortcuts,
});
