import { Component, onWillStart, proxy, t, usePlugin, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { Dialog } from "@web/core/dialog/dialog";
import { deserializeDateTime, formatDate } from "@web/core/l10n/dates";
import { NotificationPlugin } from "@web/core/notifications/notification_plugin";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class PageShortUrlsDialog extends Component {
    static template = "short_urls.PageShortUrlsDialog";
    static components = { Dialog };
    props = useProps({ close: t.function(), path: t.string(), websiteId: t.number() });

    setup() {
        this.orm = useService("orm");
        this.notification = usePlugin(NotificationPlugin);
        this.action = useService("action");
        this.state = proxy({
            links: [],
            channels: [],
            token: "",
            channelId: "",
            expire: "",
            error: "",
            editing: false,
            editToken: "",
        });
        onWillStart(() => this.load());
    }

    async load() {
        const result = await this.orm.call("short.url", "page_links", [this.props.websiteId, this.props.path]);
        this.state.links = result.links;
        this.state.channels = result.channels;
    }

    expireLabel(link) {
        return link.date_expire ? formatDate(deserializeDateTime(link.date_expire)) : "";
    }

    async copy(link) {
        await browser.navigator.clipboard.writeText(link.short_url);
        this.notification.add(`${link.short_url} copied`, { type: "success" });
    }

    async create() {
        this.state.error = "";
        try {
            await this.orm.call("short.url", "create_for_page", [this.props.websiteId, this.props.path], {
                token: this.state.token,
                channel_id: parseInt(this.state.channelId) || false,
                date_expire: this.state.expire ? `${this.state.expire} 23:59:59` : false,
            });
        } catch (error) {
            this.state.error = error.data?.message || error.message;
            return;
        }
        this.state.token = "";
        this.state.expire = "";
        await this.load();
    }

    startEdit(link) {
        this.state.editing = link.id;
        this.state.editToken = link.token;
    }

    async saveEdit(link) {
        this.state.error = "";
        try {
            await this.orm.write("short.url", [link.id], { token: this.state.editToken });
        } catch (error) {
            this.state.error = error.data?.message || error.message;
            return;
        }
        this.state.editing = false;
        await this.load();
    }

    async remove(link) {
        await this.orm.unlink("short.url", [link.id]);
        await this.load();
    }

    openList() {
        this.props.close();
        this.action.doAction("short_urls.action_short_url");
    }
}

registry.category("website_custom_menus").add("short_urls.menu_short_url_page", {
    Component: PageShortUrlsDialog,
    isDisplayed: (env) =>
        !!env.services.website.currentWebsite && env.services.website.isRestrictedEditor,
    getProps: async ({ website }) => {
        let path = "/";
        try {
            path = website.currentLocation || "/";
        } catch {
            path = "/";
        }
        return { path, websiteId: website.currentWebsite.id };
    },
});
