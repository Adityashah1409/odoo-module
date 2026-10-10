import { Component, onWillStart, proxy, usePlugin, useProps } from "@odoo/owl";
import { ORM } from "@web/core/orm_plugin";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { logError } from "../js/theme_plugin";
import { sanitizeColor } from "../js/theme_config";

const COLOR_KEYS = ["primary_color", "navbar_color", "sidebar_color", "accent_color"];

/**
 * Inline style giving a preview card its colors as CSS variables. Colors are
 * validated, and missing ones are left to the stylesheet's neutral defaults.
 *
 * @param {Object} colors e.g. { primary_color: "#1d6fb8", ... }
 */
export function presetPreviewStyle(colors) {
    return COLOR_KEYS.map((key) => {
        const color = sanitizeColor(colors?.[key]);
        return color ? `--mbt-preview-${key.split("_")[0]}: ${color};` : "";
    })
        .filter(Boolean)
        .join(" ");
}

/**
 * The color preset selection, drawn as small previews of each palette on a
 * miniature navbar, sidebar and page. Picking one sets the field, and the
 * settings' onchange fills the color fields as before.
 */
export class ColorPresetField extends Component {
    static template = "my_backend_theme.ColorPresetField";
    props = useProps({ ...standardFieldProps });

    setup() {
        this.orm = usePlugin(ORM);
        this.state = proxy({ presets: {} });
        onWillStart(async () => {
            try {
                this.state.presets = await this.orm.call("my.theme.config", "get_color_presets");
            } catch (error) {
                logError("Could not load the color presets.", error);
            }
        });
    }

    get value() {
        return this.props.record.data[this.props.name];
    }

    get cards() {
        const selection = this.props.record.fields[this.props.name].selection || [];
        return selection.map(([key, label]) => {
            let colors = this.state.presets[key];
            if (key === "custom") {
                // The colors currently in the form.
                colors = Object.fromEntries(
                    COLOR_KEYS.map((name) => [name, this.props.record.data[`mbt_${name}`]])
                );
            }
            return {
                key,
                label,
                style: presetPreviewStyle(colors),
                title: key === "custom" ? _t("Keep the colors below") : label,
            };
        });
    }

    select(key) {
        if (!this.props.readonly && key !== this.value) {
            this.props.record.update({ [this.props.name]: key });
        }
    }
}

registry.category("fields").add("mbt_color_preset", {
    component: ColorPresetField,
    supportedTypes: ["selection"],
    extractProps(_, dynamicInfo) {
        return { readonly: dynamicInfo.readonly };
    },
});
