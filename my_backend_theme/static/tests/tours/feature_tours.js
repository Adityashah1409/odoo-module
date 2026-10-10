import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("my_backend_theme_workspace", {
    steps: () => [
        { trigger: ".o_mbt_workspace .o_mbt_ws_greeting" },
        { trigger: ".o_mbt_ws_recent a:contains('Mbt Workspace Partner')" },
        { trigger: ".o_mbt_ws_bookmarks a:contains('Mbt Contacts Bookmark')" },
        {
            content: "Make the workspace the home page",
            trigger: ".o_mbt_workspace #mbt_ws_home",
            run: "click",
        },
        { trigger: ".o_mbt_workspace #mbt_ws_home:checked" },
        {
            content: "Quick create a contact from a tile",
            trigger: ".o_mbt_ws_tile[data-model='res.partner']",
            run: "click",
        },
        { trigger: ".modal .o_form_view" },
        { trigger: ".modal .o_form_button_cancel", run: "click" },
        { trigger: "body:not(:has(.modal))" },
        {
            content: "Search opens the command palette in record search",
            trigger: ".o_mbt_ws_search input",
            run: "edit Mbt Workspace",
        },
        { trigger: ".o_mbt_ws_search button[type=submit]", run: "click" },
        { trigger: ".o_command_palette .o_command:contains('Mbt Workspace Partner')" },
        { trigger: ".o_command_palette_search input", run: "press Escape" },
        { trigger: "body:not(:has(.o_command_palette))" },
        {
            content: "Turn on high contrast from the user menu",
            trigger: "button.o_user_menu",
            run: "click",
        },
        { trigger: "[data-menu='mbt_high_contrast']", run: "click" },
        { trigger: "html[data-mbt-high-contrast]" },
    ],
});

registry.category("web_tour.tours").add("my_backend_theme_color_preset", {
    steps: () => [
        { trigger: ".settings_tab [data-key='my_backend_theme']", run: "click" },
        { trigger: ".o_mbt_preset[data-preset='ocean']" },
        {
            content: "Pick the Forest preset",
            trigger: ".o_mbt_preset[data-preset='forest']",
            run: "click",
        },
        { trigger: ".o_mbt_preset_active[data-preset='forest'][aria-checked='true']" },
        { trigger: "div[name='mbt_primary_color'] input:value('#2f7d4f')" },
        // The "Custom" card previews the colors now in the form.
        { trigger: ".o_mbt_preset[data-preset='custom'][style*='#2f7d4f']" },
        { trigger: ".o_form_button_save", run: "click", expectUnloadPage: true },
        { trigger: "html[data-mbt-primary]" },
    ],
});
