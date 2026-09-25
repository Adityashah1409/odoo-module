# Backend Theme (`my_backend_theme`)

A configurable theme and productivity toolkit for the **Odoo 20** backend (web
client), written from scratch. It contains no code, templates, styles, icons or
branding from any third-party theme.

With nothing configured, the module keeps Odoo's own look. Every visual change
is opt-in from *Settings → Backend Theme*.

## Features

### Look and feel

| Feature | Where | Notes |
| --- | --- | --- |
| Color presets and custom colors | Settings | Primary, navbar, sidebar and accent colors; 6 original presets. Text colors switch automatically for contrast. |
| Dark mode | Settings, user menu, user preferences | Light, dark or follow the device. Uses Odoo's own dark stylesheet; each user chooses. |
| Menu style | Settings | Odoo's top bar, sidebar, compact sidebar or icon-only sidebar. The sidebar has a menu search, collapses, expands on hover and remembers its state per user. |
| App icon style | Settings | Original, rounded, circle, monochrome, glass, outlined. |
| Compact navbar | Settings | Lower top bar. |
| Font and UI scale | Settings, user preferences | Font stacks (no downloads); 90 to 120 % scale, per user if wanted. |
| List views | Settings | Compact/comfortable density, striped rows, borderless. |
| Form views | Settings | Card, flat or compact form, sticky status bar on/off, chatter position (with `my_backend_theme_mail`). |
| Controls | Settings | Button, checkbox and scrollbar styles, rounded fields. |
| Reduce motion | Settings, user preferences | Turns animations off; the OS preference is always honoured. |

### Productivity

| Feature | Default shortcut | Notes |
| --- | --- | --- |
| Quick Create (top bar) | `Alt+Shift+N` | Opens a creation form in a dialog. Entries are managed by administrators (Settings app menu *Backend Theme → Quick Create*) and only shown to users allowed to create those records. "Add Suggested Entries" fills it with the installed apps. |
| Bookmarks (top bar) | `Alt+Shift+B` | Bookmark any backend page. Private to each user. |
| Recently viewed (top bar) | `Alt+Shift+R` | Records the user opened, newest first, with a configurable limit. |
| Workspace tabs | `Alt+Shift+T` (duplicate tab) | Off by default. Tabs below the navbar with new, duplicate, pin, reload, close others/right/all, drag to reorder, middle click to close. Each browser tab has its own workspace; pinned tabs return in new windows. |
| Split view | – | Gear menu of any list or kanban view, or the command palette. The list stays on one side and the selected record's form on the other; the divider can be dragged. Survives reloads. |
| Record search | `Alt+Shift+F` | In the command palette, type `?` and a name: searches the models chosen in the Settings app menu *Backend Theme → Global Search Models*. |
| Theme commands | `Ctrl+K` | Dark/light mode, bookmark this page, bookmarks, quick create, recent records, split view, open in a new browser tab, theme settings. |
| Dark mode toggle | `Alt+Shift+D` | |

Shortcuts can be changed or turned off (`none`) in *Settings → Backend Theme →
Keyboard Shortcuts*. They are written like `alt+shift+k` or `ctrl+alt+k`;
Odoo's built-in `Alt+Shift+…` shortcuts (search panel, share, switch company…)
are not used. Every link the theme shows keeps the browser's
`Ctrl+click`/middle click to open a new browser tab.

### Mobile and tablets

* Phones: the sidebar is replaced by Odoo's own menu, tabs are hidden, split
  view stacks the list above the form.
* Tablets and small laptops (below 1200 px): the sidebar starts as icons and
  can be expanded for the session.
* Odoo 20 already ships an installable web app (PWA). The theme sets its title
  bar color and the mobile browser bar to the navbar color.

## Modules

| Module | Depends on | Purpose |
| --- | --- | --- |
| `my_backend_theme` | `web`, `base_setup` | Everything above. |
| `my_backend_theme_mail` | `my_backend_theme`, `mail` | Chatter position setting. Installs itself when both are installed. |

## Installation

1. Put both directories in a folder listed in your Odoo `addons_path`.
2. Update the apps list, then install **Backend Theme**, or:

   ```bash
   odoo-bin -d <database> -i my_backend_theme
   ```

3. After pulling new code: `odoo-bin -d <database> -u my_backend_theme`.

## Configuration

* **Company settings:** *Settings → Backend Theme* (administrators). Changes
  apply when the page reloads, which Odoo does after saving.
* **User preferences:** avatar menu → *My Preferences → Backend Theme* (color
  scheme, UI scale, reduce motion, sidebar collapsed), and the *Dark mode*
  switch in the avatar menu.
* **Quick Create and Global Search models:** Settings app menu *Backend
  Theme*, or the *Add Suggested Entries* button in the settings.

## Security

* Company settings are `ir.config_parameter` records written through
  `res.config.settings` (administrators only). Every value is validated when
  saved, again when sent to the browser, and colors a third time in
  JavaScript, so a hand-edited parameter can only fall back to its default.
* Bookmarks and recently viewed records have record rules limiting every user
  to their own rows (`security/ir.access.csv`). A bookmark only accepts
  relative `/odoo…` URLs, so it can't be turned into an external or
  `javascript:` link.
* Nothing runs as superuser on business data. Quick Create lists a model only
  if the user may create its records; recently viewed, bookmarks and record
  search check read access (and record rules and companies) for every record.
* Quick Create contexts are Python literals parsed with `ast.literal_eval`,
  never evaluated. Icons are restricted to icon names.
* Workspace tabs are stored in the browser (session/local storage); stored
  data is re-validated when read.

## Performance

* The theme itself is CSS attributes and variables on `<html>`; nothing
  re-renders Odoo's views.
* Bookmarks, recent records and quick create entries are loaded on first use
  and cached; recently viewed tracking is one small call per record opened.
* Record search is debounced, needs at least 2 characters and returns a
  configurable number of results per model.

## Accessibility

* Menus, tabs and palette entries are keyboard reachable, with labels for
  icon-only buttons, `role="tablist"`/`tab` on workspace tabs and a keyboard
  resizable split view divider (arrow keys).
* Automatic text colors keep contrast on custom colors.
* Reduce motion (setting or OS preference) turns transitions off.

## Tests

```bash
odoo-bin -d <test-db> -i my_backend_theme --test-enable \
    --test-tags /my_backend_theme --stop-after-init
```

The suite covers configuration validation, per-user privacy of bookmarks and
recent records, access filtering of quick create and record search, shortcut
validation, the web manifest and the dark stylesheet selection. It also runs
the JavaScript unit tests (`static/tests`, Hoot) in a headless browser, which
needs Chrome/Chromium and the `websocket-client` Python package.

## Developer architecture

```
Server                                      Web client (OWL 3)
------                                      ------------------
res.config.settings ─┐
  (ir.config_parameter)                     session.backend_theme ─┐
                     ├─ my.theme.config ──► ir.http.session_info   ├─► ThemePlugin
res.users.settings ──┴──────────────────────► user.settings ───────┘   │
  (per-user prefs)                                                     ├─► data-mbt-* / --mbt-* on <html>
                                                                       ├─► Sidebar, WorkspaceTabs (main components)
my.theme.bookmark / .recent / .quick.create ◄─── NavigationPlugin ◄────┤   Systray menus, SplitView
my.theme.search.model.global_search ◄──── command palette providers ◄──┘
```

* `models/theme_config.py`: allowed values, validators and
  `my.theme.config._get_global_config()`, the one place the global
  configuration is read.
* `static/src/js/theme_config.js`: pure functions merging global and user
  settings into attributes and CSS variables (unit tested).
* `static/src/js/theme_plugin.js`: the theme service. Odoo 20 replaced
  `registry.category("services")` services with OWL 3 plugins
  (`services.add(Plugin)`); features read settings from it:

  ```js
  import { usePlugin } from "@odoo/owl";
  import { ThemePlugin } from "@my_backend_theme/js/theme_plugin";

  const theme = usePlugin(ThemePlugin);
  theme.get("menu_style");                         // reactive (computed signal)
  await theme.setUserPreference("mbt_ui_scale", "110");
  ```

* `static/src/navigation/`: `NavigationPlugin` (current page, bookmarks,
  recent tracking, quick create) and the three top bar menus.
* `static/src/tabs/`: `TabStore` (pure, unit tested) and the tab bar.
* `static/src/split_view/`: the split view client action and its gear menu
  entry.
* `static/src/commands/`: command palette providers and global shortcuts.
* SCSS rules are scoped to `html[data-mbt-*]` attributes, so unconfigured
  features never touch Odoo's styles.
* Only one Odoo method is patched: `FormRenderer.mailLayout` in
  `my_backend_theme_mail`, to place the chatter. Everything else uses
  registries (systray, main components, user menu, cog menu, command
  providers, actions).

### Odoo 20 differences this module follows

* Services are OWL 3 plugins (`Plugin`, `signal`, `computed`, `useEffect`).
* Access rights and record rules live together in `security/ir.access.csv`.
* User-editable `res.users` fields use `user_writeable=True`.
* Config parameters are typed (`get_str`, `get_bool`, `get_int`).
* Hotkeys are written with modifiers in the order `alt`, `control`, `shift`.

## Known limitations

* Fonts are not downloaded: a font is used only if the device has it.
* Switching light/dark reloads the page, because Odoo serves a separate dark
  stylesheet.
* Split view keeps the source action's domain but not the filters typed in
  the list before opening it after a page reload.
* Workspace tabs remember pages, not unsaved edits: leaving a tab saves or
  discards a form like any other navigation in Odoo.
* Tested on Odoo 20.0 Community. Not yet tested on Enterprise.

## Troubleshooting

* **Nothing changes after saving:** reload the page.
* **The backend looks wrong:** *Settings → Backend Theme → Reset to Defaults*.
  If the web client does not load at all, uninstall from `odoo-bin shell -d <db>`:
  `env['ir.module.module'].search([('name', '=', 'my_backend_theme')]).button_immediate_uninstall()`.
* **A shortcut does nothing:** another shortcut may use the same keys; change
  it in the settings. `Ctrl+Alt` shortcuts don't work inside text fields
  because many keyboard layouts type characters with them.
* Theme errors are logged in the browser console with the prefix
  `[my_backend_theme]` and never stop Odoo from loading.

## License

LGPL-3
