# Backend Theme (`my_backend_theme`)

A configurable theme for the **Odoo 20** backend (web client), written from
scratch. It contains no code, templates, styles, icons or branding from any
third-party theme.

The module is built in phases (see [Roadmap](#roadmap)). This is **Phase 1**:
the foundation that every later feature plugs into.

## Features (Phase 1)

| Setting | Scope | Effect |
| --- | --- | --- |
| Primary color | Company | Primary buttons, links, checkboxes, focus borders |
| Navbar color | Company | Top bar background; text switches to white or dark for contrast |
| Font | Company | Font stack (System, Inter, Roboto, Open Sans, Poppins) |
| Default UI scale | Company | 90 / 100 / 110 / 120 % of the whole interface |
| Reduce motion | Company | Turns off animations and transitions for everyone |
| UI scale | User | Overrides the company default for one user |
| Reduce motion | User | Turns off animations for one user |
| Reset to defaults | Company | Removes every theme setting (user preferences are kept) |
| Reset my theme preferences | User | Clears the user's own overrides |

The operating system's *reduce motion* preference (`prefers-reduced-motion`)
is always honoured.

Leaving a color empty keeps Odoo's own color. With nothing configured the
module changes nothing visually.

## Installation

1. Put this directory in a folder listed in your Odoo `addons_path`.
2. Update the apps list, then install **Backend Theme**, or from the command line:

   ```bash
   odoo-bin -d <database> -i my_backend_theme
   ```

3. To upgrade after pulling new code:

   ```bash
   odoo-bin -d <database> -u my_backend_theme
   ```

Dependencies: `web`, `base_setup` (both part of Odoo Community). No business
app (Sales, CRM, Accounting...) is required.

## Configuration

* **Company settings:** *Settings → Backend Theme* (administrators only).
* **User preferences:** avatar menu → *My Preferences → Backend Theme*.

Changes apply after the page reloads, which Odoo does automatically when
settings are saved.

## Security

* Company settings are `ir.config_parameter` records written through
  `res.config.settings`, so only Settings administrators can change them.
* User preferences are stored on `res.users.settings`, whose existing record
  rules already limit every user to their own row. The module adds no new
  model that needs access rights.
* Colors are validated (`#rrggbb` only) when saved, validated again when sent
  to the browser, and a third time in JavaScript. A hand-edited parameter can
  therefore only fall back to the default, never inject CSS.

## Compatibility

* Built and tested on **Odoo 20.0 Community**. Not yet tested on Enterprise.
* Browsers need CSS `color-mix()` support for hover shades (Chrome/Edge 111+,
  Firefox 113+, Safari 16.2+).

## Developer architecture

```
Server                                      Web client (OWL 3)
------                                      ------------------
res.config.settings ─┐
  (ir.config_parameter)                     session.backend_theme ─┐
                     ├─ my.theme.config ──► ir.http.session_info   ├─► ThemePlugin
res.users.settings ──┴──────────────────────► user.settings ───────┘     │
  (per-user prefs)                                                       ▼
                                             data-mbt-* attributes and --mbt-* CSS
                                             variables on <html> ─► backend.scss
```

* `models/theme_config.py` holds the allowed values, the validators and
  `my.theme.config._get_global_config()`, the one place the global
  configuration is read.
* `static/src/js/theme_config.js` contains pure functions that merge global and
  user settings and turn them into attributes and CSS variables.
* `static/src/js/theme_plugin.js` is the **theme service**. Odoo 20 replaced
  `registry.category("services")` services with OWL 3 *plugins*
  (`services.add(Plugin)`). Other theme features read settings from it:

  ```js
  import { usePlugin } from "@odoo/owl";
  import { ThemePlugin } from "@my_backend_theme/js/theme_plugin";

  const theme = usePlugin(ThemePlugin);
  theme.get("ui_scale");                        // reactive (computed signal)
  await theme.setUserPreference("mbt_ui_scale", "110");
  ```

* `static/src/scss/backend.scss` only contains rules scoped to a
  `html[data-mbt-*]` attribute, so unconfigured features never touch Odoo's
  styles. Bootstrap components are recolored through their CSS variables
  (Odoo compiles Bootstrap with an empty prefix: `--primary`, `--btn-bg`...).

### Differences from earlier Odoo versions

* Services are OWL 3 plugins (`Plugin`, `signal`, `computed`, `useEffect`)
  instead of `{ start() }` objects in the services registry.
* Access rights use `security/ir.access.csv` (ACLs and record rules in one
  file) instead of `ir.model.access.csv` + `ir.rule` records.
* User-editable `res.users` fields are declared with `user_writeable=True`
  instead of `SELF_WRITEABLE_FIELDS`.
* Config parameters are typed (`get_str`, `get_bool`, `get_int`).

### Tests

```bash
odoo-bin -d <test-db> -i my_backend_theme --test-enable --test-tags /my_backend_theme --stop-after-init
```

## Known limitations

* The font setting does not download fonts: the chosen font is used only when
  it is installed on the user's device, otherwise the system font is shown.
* A few elements with colors compiled into Odoo's SCSS (for example the search
  bar border) keep Odoo's color until Phase 2's color system.
* Dark mode is not part of Phase 1.

## Troubleshooting

* **Nothing changes after saving:** reload the page; check that the value is a
  six-digit hex color such as `#1f6feb`.
* **The backend looks wrong:** use *Settings → Backend Theme → Reset to
  Defaults*. If the web client does not load at all, uninstall the module
  from `odoo-bin shell -d <db>`:
  `env['ir.module.module'].search([('name', '=', 'my_backend_theme')]).button_immediate_uninstall()`.
* Theme errors are logged in the browser console with the prefix
  `[my_backend_theme]` and never stop Odoo from loading.

## Roadmap

1. **Module skeleton, settings, theme service, base styles** (this release)
2. Navbar, sidebar, menu styles, full color system, dark mode
3. List view, form view, sticky headers, chatter position
4. Quick create, bookmarks, recently viewed
5. Tabs, open in new browser tab, split form
6. Global search, command palette, keyboard shortcuts
7. Responsive/mobile layouts, optional PWA module
8. Security, performance and accessibility hardening, documentation

## License

LGPL-3
