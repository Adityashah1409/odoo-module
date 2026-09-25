import { usePlugin } from "@odoo/owl";
import { SIZES } from "@web/core/ui/ui_utils";
import { patch } from "@web/core/utils/patch";
import { FormRenderer } from "@web/views/form/form_renderer";
import { logError, ThemePlugin } from "@my_backend_theme/js/theme_plugin";

/** Layouts where the chatter sits beside the form, and their bottom equivalent. */
const SIDE_TO_BOTTOM = {
    SIDE_CHATTER: "BOTTOM_CHATTER",
    EXTERNAL_COMBO_XXL: "EXTERNAL_COMBO",
};

/**
 * Odoo decides where the chatter goes in `mailLayout` (added by the mail
 * module) and offers no other hook for it, so this is the one place the theme
 * patches a method. Any error falls back to Odoo's own layout.
 */
patch(FormRenderer.prototype, {
    setup() {
        super.setup();
        this.mbtTheme = usePlugin(ThemePlugin);
    },

    mailLayout(hasAttachmentContainer) {
        const layout = super.mailLayout(hasAttachmentContainer);
        try {
            const position = this.mbtTheme.get("chatter_position");
            if (position === "bottom") {
                return SIDE_TO_BOTTOM[layout] || layout;
            }
            // Odoo only puts the chatter aside from XXL screens; "side" also
            // does it on XL screens.
            if (position === "side" && this.uiService.size === SIZES.XL) {
                if (layout === "BOTTOM_CHATTER") {
                    return hasAttachmentContainer && this.hasFile() ? "COMBO" : "SIDE_CHATTER";
                }
                if (layout === "EXTERNAL_COMBO") {
                    return "EXTERNAL_COMBO_XXL";
                }
            }
        } catch (error) {
            logError("Could not apply the chatter position.", error);
        }
        return layout;
    },
});
