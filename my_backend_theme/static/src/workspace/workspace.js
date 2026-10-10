import { Component, onWillStart, proxy, usePlugin, useProps } from "@odoo/owl";
import { ORM } from "@web/core/orm_plugin";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { logError, ThemePlugin } from "../js/theme_plugin";
import { NavigationPlugin, onThemeLinkClick, recordUrl } from "../navigation/navigation_plugin";
import { SEARCH_NAMESPACE } from "../commands/theme_commands";

export const WORKSPACE_TAG = "my_backend_theme.workspace";
export const WORKSPACE_ACTION = "my_backend_theme.action_my_theme_workspace";
const RECENT_SHOWN = 12;

/**
 * Part of the day used for the greeting.
 *
 * @param {number} hour 0-23
 * @returns {"morning"|"afternoon"|"evening"}
 */
export function dayPart(hour) {
    if (hour < 5 || hour >= 18) {
        return "evening";
    }
    return hour < 12 ? "morning" : "afternoon";
}

function greeting(name) {
    const part = dayPart(new Date().getHours());
    if (part === "morning") {
        return _t("Good morning, %(name)s", { name });
    }
    if (part === "afternoon") {
        return _t("Good afternoon, %(name)s", { name });
    }
    return _t("Good evening, %(name)s", { name });
}

/**
 * A personal home page gathering what the theme knows about the user: the
 * records they can create, their bookmarks and what they opened recently.
 * Each section follows its feature's setting and loads independently, so
 * one failing list never hides the others.
 */
export class Workspace extends Component {
    static template = "my_backend_theme.Workspace";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.theme = usePlugin(ThemePlugin);
        this.navigation = usePlugin(NavigationPlugin);
        this.orm = usePlugin(ORM);
        this.command = useService("command");
        this.state = proxy({
            query: "",
            isHome: false,
            errors: {},
        });
        this.greeting = greeting(user.name);

        onWillStart(() =>
            Promise.all([
                this.load("quickCreate", "enable_quick_create", () =>
                    this.navigation.loadQuickCreateItems()
                ),
                this.load("bookmarks", "enable_bookmarks", () => this.navigation.loadBookmarks()),
                this.load("recent", "enable_recent", () => this.navigation.loadRecent(true)),
                this.orm.silent
                    .call("res.users", "mbt_is_workspace_home")
                    .then((isHome) => (this.state.isHome = isHome))
                    .catch((error) => logError("Could not read the home page.", error)),
            ])
        );
    }

    async load(section, settingKey, loader) {
        if (!this.theme.get(settingKey)) {
            return;
        }
        try {
            await loader();
        } catch (error) {
            this.state.errors[section] = true;
            logError(`Could not load ${section}.`, error);
        }
    }

    get isEnabled() {
        return this.theme.get("enable_workspace");
    }

    get quickCreateItems() {
        return this.theme.get("enable_quick_create") ? this.navigation.quickCreateItems() || [] : [];
    }

    get bookmarks() {
        return this.theme.get("enable_bookmarks") ? this.navigation.bookmarks() || [] : [];
    }

    get recent() {
        return this.theme.get("enable_recent")
            ? (this.navigation.recent() || []).slice(0, RECENT_SHOWN)
            : [];
    }

    recordUrl(entry) {
        return recordUrl(entry.res_model, entry.res_id);
    }

    viewedWhen(entry) {
        try {
            return deserializeDateTime(entry.last_viewed).toRelative() || "";
        } catch {
            return "";
        }
    }

    onLinkClick(ev) {
        onThemeLinkClick(ev);
    }

    onQueryInput(ev) {
        this.state.query = ev.target.value;
    }

    onSearch(ev) {
        ev.preventDefault();
        this.command.openMainPalette({ searchValue: `${SEARCH_NAMESPACE}${this.state.query.trim()}` });
    }

    removeLabel(bookmark) {
        return _t("Remove %(name)s", { name: bookmark.name });
    }

    async removeBookmark(bookmark) {
        try {
            await this.navigation.removeBookmark(bookmark.id);
        } catch (error) {
            this.state.errors.bookmarks = true;
            logError("Could not remove the bookmark.", error);
        }
    }

    async toggleHome() {
        const enabled = !this.state.isHome;
        try {
            await this.orm.call("res.users", "mbt_set_workspace_home", [enabled]);
            this.state.isHome = enabled;
        } catch (error) {
            logError("Could not change the home page.", error);
        }
    }
}

registry.category("actions").add(WORKSPACE_TAG, Workspace);
