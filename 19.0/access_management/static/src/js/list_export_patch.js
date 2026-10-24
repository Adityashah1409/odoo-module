import { ListController } from "@web/views/list/list_controller";
import { patch } from "@web/core/utils/patch";

// a list whose arch says export_xlsx="0" (set by an access rule) also hides "Export" in the action menu
patch(ListController.prototype, {
    get isExportEnable() {
        return Boolean(this._amExportEnable) && this.props.archInfo.activeActions?.exportXlsx !== false;
    },
    set isExportEnable(value) {
        this._amExportEnable = value;
    },
});
