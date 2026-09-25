import {
    Component,
    onWillStart,
    proxy,
    useListener,
    usePlugin,
    useProps,
    xml,
} from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { makeContext } from "@web/core/context";
import { Domain } from "@web/core/domain";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useSubEnv } from "@web/owl2/utils";
import { STATIC_ACTIONS_GROUP_NUMBER } from "@web/search/action_menus/action_menus";
import { View } from "@web/views/view";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { startupConfig, ThemePlugin } from "../js/theme_plugin";
import { recordUrl } from "../navigation/navigation_plugin";

export const SPLIT_VIEW_TAG = "my_backend_theme.split_view";

const MODEL_RE = /^[a-z0-9_]+(\.[a-z0-9_]+)*$/;
const WIDTH_STORAGE_KEY = "mbt_split_width";
const MIN_WIDTH = 25;
const MAX_WIDTH = 75;

function readListWidth() {
    try {
        const width = Number(browser.localStorage.getItem(WIDTH_STORAGE_KEY));
        return width >= MIN_WIDTH && width <= MAX_WIDTH ? width : 40;
    } catch {
        return 40;
    }
}

/**
 * Renders one view with its own copy of the environment's configuration:
 * views write their type and arch into `env.config`, so two views side by
 * side must not share it.
 */
class SplitPane extends Component {
    static template = xml`<View t-props="this.props.viewProps"/>`;
    static components = { View };
    props = useProps();

    setup() {
        useSubEnv({ config: { ...this.env.config, ...this.props.config } });
    }
}

/**
 * List of records on one side, the selected record's form on the other, so
 * users can go through records without losing their place in the list.
 */
export class SplitView extends Component {
    static template = "my_backend_theme.SplitView";
    static components = { SplitPane };
    static path = "split";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.action = useService("action");
        this.theme = usePlugin(ThemePlugin);
        const params = this.props.action.params || {};
        const context = this.props.action.context || {};
        this.resModel = MODEL_RE.test(params.split_model || "") ? params.split_model : null;
        this.sourceActionId = Number.isInteger(Number(params.split_action))
            ? Number(params.split_action) || false
            : false;
        this.domain = Array.isArray(params.domain) ? params.domain : [];
        this.context = { ...context };
        this.listViewId = false;
        this.formViewId = false;
        this.searchViewId = false;
        this.state = proxy({
            resId: Number.isInteger(params.resId) ? params.resId : false,
            formOpen: Number.isInteger(params.resId),
            formKey: 0,
            formName: "",
            listKey: 0,
            listWidth: readListWidth(),
            resizing: false,
        });

        onWillStart(async () => {
            if (this.sourceActionId) {
                // Use the views of the action the split view was opened from,
                // and its domain when reopened from the URL.
                try {
                    const source = await this.action.loadAction(this.sourceActionId);
                    if (source?.res_model === this.resModel && !params.domain) {
                        const evalContext = { ...user.context, uid: user.userId };
                        this.domain = source.domain
                            ? new Domain(source.domain).toList(evalContext)
                            : [];
                        const sourceContext =
                            typeof source.context === "string"
                                ? makeContext([source.context], evalContext)
                                : source.context || {};
                        this.context = { ...sourceContext, ...this.context };
                    }
                    if (source?.res_model === this.resModel) {
                        this.sourceName = source.display_name || source.name;
                        const viewId = (type) => source.views?.find((v) => v[1] === type)?.[0];
                        this.listViewId = viewId("list") || false;
                        this.formViewId = viewId("form") || false;
                        this.searchViewId = source.search_view_id?.[0] || false;
                    }
                } catch {
                    // Keep the model's records without the action's domain.
                }
            }
            // Reopened from the URL, the action has no name of its own.
            if (!this.env.config.getDisplayName?.()) {
                this.env.config.setDisplayName?.(this.sourceName || _t("Split View"));
            }
        });

        useListener(browser, "pointermove", (ev) => this.onResize(ev));
        useListener(browser, "pointerup", () => this.stopResize());
        this.updateUrl();
    }

    get isEnabled() {
        return this.theme.get("enable_split_view");
    }

    get listPaneProps() {
        return {
            config: {},
            viewProps: {
                type: "list",
                resModel: this.resModel,
                viewId: this.listViewId,
                searchViewId: this.searchViewId,
                domain: this.domain,
                context: this.context,
                display: { controlPanel: {} },
                loadIrFilters: true,
                selectRecord: (resId, options = {}) => this.selectRecord(resId, options),
                createRecord: () => this.selectRecord(false),
            },
        };
    }

    get formPaneProps() {
        return {
            config: {
                breadcrumbs: [],
                // The form's name must not rename the split view itself.
                setDisplayName: (name) => (this.state.formName = name || ""),
                getDisplayName: () => this.state.formName,
                historyBack: () => this.closeForm(),
            },
            viewProps: {
                type: "form",
                noBreadcrumbs: true,
                resModel: this.resModel,
                viewId: this.formViewId,
                resId: this.state.resId || false,
                context: this.context,
                display: { controlPanel: {} },
                onSave: () => this.refreshList(),
            },
        };
    }

    updateUrl() {
        this.props.updateActionState?.({
            split_model: this.resModel || undefined,
            split_action: this.sourceActionId || undefined,
            resId: this.state.resId || undefined,
        });
    }

    selectRecord(resId, { newWindow } = {}) {
        if (newWindow && resId) {
            browser.open(recordUrl(this.resModel, resId), "_blank");
            return;
        }
        this.state.resId = resId;
        this.state.formOpen = true;
        // A new key remounts the form, which saves the previous record first
        // through Odoo's usual "leave" handling.
        this.state.formKey++;
        this.updateUrl();
    }

    closeForm() {
        this.state.resId = false;
        this.state.formOpen = false;
        this.state.formKey++;
        this.updateUrl();
    }

    refreshList() {
        this.state.listKey++;
    }

    openFullForm() {
        if (this.state.resId) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: this.resModel,
                res_id: this.state.resId,
                views: [[false, "form"]],
            });
        }
    }

    startResize(ev) {
        ev.preventDefault();
        this.rootEl = ev.currentTarget.closest(".o_mbt_split");
        this.state.resizing = true;
    }

    onResize(ev) {
        if (!this.state.resizing || !this.rootEl) {
            return;
        }
        const rect = this.rootEl.getBoundingClientRect();
        const isRtl = document.documentElement.dir === "rtl";
        const offset = isRtl ? rect.right - ev.clientX : ev.clientX - rect.left;
        const width = Math.round((offset / rect.width) * 100);
        this.state.listWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, width));
    }

    stopResize() {
        if (!this.state.resizing) {
            return;
        }
        this.state.resizing = false;
        try {
            browser.localStorage.setItem(WIDTH_STORAGE_KEY, String(this.state.listWidth));
        } catch {
            // Not remembering the width is fine.
        }
    }

    onResizeKeydown(ev) {
        const step = { ArrowLeft: -5, ArrowRight: 5 }[ev.key];
        if (step) {
            ev.preventDefault();
            const width = this.state.listWidth + step;
            this.state.listWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, width));
            this.stopResize();
        }
    }
}

registry.category("actions").add(SPLIT_VIEW_TAG, SplitView);

/**
 * Action opening the split view for the records of a list or kanban view.
 *
 * @param {Object} env a view's environment
 */
export function splitViewAction(env) {
    const config = env.config || {};
    const actionId = Number.isInteger(config.actionId) ? config.actionId : false;
    return {
        type: "ir.actions.client",
        tag: SPLIT_VIEW_TAG,
        name: config.getDisplayName?.() || _t("Split View"),
        params: {
            split_model: env.searchModel.resModel,
            split_action: actionId,
            domain: env.searchModel.domain,
        },
        context: env.searchModel.context || {},
    };
}

export class SplitViewCogMenuItem extends Component {
    static template = xml`
        <DropdownItem class="'o_mbt_split_view_menu'" onSelected.bind="this.open">
            <i class="oi oi-fw me-1" data-icon="dock_to_right"/>Split View
        </DropdownItem>`;
    static components = { DropdownItem };

    setup() {
        this.action = useService("action");
    }

    open() {
        this.action.doAction(splitViewAction(this.env));
    }
}

registry.category("cogMenu").add(
    "my_backend_theme.split_view",
    {
        Component: SplitViewCogMenuItem,
        groupNumber: STATIC_ACTIONS_GROUP_NUMBER,
        isDisplayed: (env) =>
            ["list", "kanban"].includes(env.config?.viewType) &&
            Boolean(env.searchModel?.resModel) &&
            env.searchModel.resModel !== "res.config.settings" &&
            startupConfig().enable_split_view,
    },
    { sequence: 40 }
);
