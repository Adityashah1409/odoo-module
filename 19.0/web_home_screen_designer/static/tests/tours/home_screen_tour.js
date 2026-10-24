import { registry } from "@web/core/registry";

function setRange(name, value) {
    return {
        content: `set ${name} to ${value}`,
        trigger: `.o_hs_designer input[name=${name}]`,
        run() {
            this.anchor.value = value;
            this.anchor.dispatchEvent(new Event("input", { bubbles: true }));
        },
    };
}

registry.category("web_tour.tours").add("web_home_screen_designer_tour", {
    steps: () => [
        { content: "home screen with apps", trigger: '.o_home_screen .o_hs_app[data-menu-xmlid="base.menu_administration"]' },
        { content: "clock", trigger: ".o_hs_clock" },
        { content: "greeting", trigger: ".o_hs_greeting:contains(Mitchell)" },
        { content: "search an app", trigger: ".o_hs_search input", run: "edit sett" },
        {
            content: "only Settings left",
            trigger: '.o_hs_grid:has(.o_hs_app[data-menu-xmlid="base.menu_administration"]):not(:has(.o_hs_app[data-menu-xmlid="base.menu_management"]))',
        },
        { content: "search a menu", trigger: ".o_hs_search input", run: "edit Users" },
        { content: "menu result", trigger: ".o_hs_menu_result:contains(Users)" },
        { content: "clear", trigger: ".o_hs_search input", run: "clear" },
        { content: "open designer", trigger: ".o_hs_designer_toggle", run: "click" },
        { content: "sunset gradient", trigger: '.o_hs_swatch[data-value="sunset"]', run: "click" },
        { content: "preview updated", trigger: ".o_home_screen.o_hs_gradient_sunset" },
        setRange("columns", 4),
        { content: "4 columns", trigger: ".o_home_screen.o_hs_fixed_columns" },
        { content: "hide Apps", trigger: '.o_hs_app[data-menu-xmlid="base.menu_management"] .o_hs_toggle_app', run: "click" },
        { content: "Apps greyed", trigger: '.o_hs_app.o_hs_app_hidden[data-menu-xmlid="base.menu_management"]' },
        {
            content: "move Settings first",
            trigger: '.o_hs_app[data-menu-xmlid="base.menu_administration"] .o_hs_move_left',
            run() {
                // click until Settings is the first tile
                for (let i = 0; i < 20; i++) {
                    const first = document.querySelector(".o_hs_grid .o_hs_app");
                    if (first.dataset.menuXmlid === "base.menu_administration") {
                        break;
                    }
                    document
                        .querySelector('.o_hs_app[data-menu-xmlid="base.menu_administration"] .o_hs_move_left')
                        .click();
                }
            },
        },
        { content: "save for me", trigger: ".o_hs_save_user", run: "click" },
        { content: "designer closed", trigger: ".o_home_screen:not(.o_hs_designing)" },
        {
            content: "Apps hidden",
            trigger: '.o_hs_grid:has(.o_hs_app[data-menu-xmlid="base.menu_administration"]):not(:has(.o_hs_app[data-menu-xmlid="base.menu_management"]))',
        },
        { content: "open Settings", trigger: '.o_hs_app[data-menu-xmlid="base.menu_administration"] .o_hs_app_link', run: "click" },
        { content: "settings opened", trigger: ".o_setting_container, .o_settings_container, .settings" },
    ],
});
