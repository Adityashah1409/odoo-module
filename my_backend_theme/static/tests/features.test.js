import { describe, expect, test } from "@odoo/hoot";
import { computeRootState, resolveConfig } from "@my_backend_theme/js/theme_config";
import { presetPreviewStyle } from "@my_backend_theme/settings/color_preset_field";
import { dayPart } from "@my_backend_theme/workspace/workspace";

describe.current.tags("headless");

test("high contrast: company default or the user's own choice", () => {
    expect(resolveConfig().high_contrast).toBe(false);
    expect(resolveConfig({ high_contrast: true }).high_contrast).toBe(true);
    expect(resolveConfig({}, { mbt_high_contrast: true }).high_contrast).toBe(true);
    // A user cannot turn off what the company turned on for everyone.
    expect(resolveConfig({ high_contrast: true }, { mbt_high_contrast: false }).high_contrast).toBe(
        true
    );
    const { attributes } = computeRootState(resolveConfig({}, { mbt_high_contrast: true }));
    expect(attributes["data-mbt-high-contrast"]).toBe("");
});

test("large UI scales", () => {
    const config = resolveConfig({ ui_scale: "130" }, { mbt_ui_scale: "140" });
    expect(config.ui_scale).toBe(140);
    expect(computeRootState(config).variables["--mbt-ui-scale"]).toBe("1.4");
    expect(resolveConfig({ ui_scale: "150" }).ui_scale).toBe(100);
});

test("preset previews only use valid colors", () => {
    expect(
        presetPreviewStyle({
            primary_color: "#1D6FB8",
            navbar_color: "red; background: url(x)",
            sidebar_color: false,
            accent_color: "#38bdf8",
        })
    ).toBe("--mbt-preview-primary: #1d6fb8; --mbt-preview-accent: #38bdf8;");
    expect(presetPreviewStyle(undefined)).toBe("");
});

test("workspace greeting follows the time of day", () => {
    expect(dayPart(8)).toBe("morning");
    expect(dayPart(14)).toBe("afternoon");
    expect(dayPart(21)).toBe("evening");
    expect(dayPart(2)).toBe("evening");
});
