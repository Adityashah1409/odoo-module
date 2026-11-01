import { SIZES } from "@web/core/ui/ui_service";
import { patch } from "@web/core/utils/patch";
import { FormRenderer } from "@web/views/form/form_renderer";

import { chatterPrefs } from "./chatter_prefs";

const TO_BOTTOM = { SIDE_CHATTER: "BOTTOM_CHATTER", EXTERNAL_COMBO_XXL: "EXTERNAL_COMBO" };
const TO_SIDE = { BOTTOM_CHATTER: "SIDE_CHATTER", EXTERNAL_COMBO: "EXTERNAL_COMBO_XXL" };

patch(FormRenderer.prototype, {
    mailLayout(hasAttachmentContainer) {
        const layout = super.mailLayout(hasAttachmentContainer);
        if (chatterPrefs.position === "bottom") {
            return TO_BOTTOM[layout] || layout;
        }
        if (chatterPrefs.position === "side" && this.uiService.size >= SIZES.LG) {
            return TO_SIDE[layout] || layout;
        }
        return layout;
    },
});
