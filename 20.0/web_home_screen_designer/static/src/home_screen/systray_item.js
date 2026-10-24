import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class HomeScreenSystray extends Component {
    static template = "web_home_screen_designer.Systray";

    setup() {
        this.action = useService("action");
    }

    open() {
        this.action.doAction("web_home_screen_designer.action_home_screen", { clearBreadcrumbs: true });
    }
}

registry.category("systray").add("web_home_screen_designer.home", { Component: HomeScreenSystray }, { sequence: 100 });
