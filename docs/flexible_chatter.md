# Flexible Chatter (`flexible_chatter`)

Chatter position, width and folding per user for **Odoo 19.0 / 20.0**.

The code lives in:
- `19.0/flexible_chatter/`;
- `20.0/flexible_chatter/`.

---

## 1. Planning

### 1.1 Goal

Odoo puts the chatter on the side only on extra-large screens (≥ 1400 px) and with a fixed width; on laptops
it always goes below the form, and on wide screens it always takes the side. People want to choose: the chatter
next to the form on a 13" laptop, below the form on a 27" screen for wide lists, wider for long e-mails, or out of
the way while filling a big form.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | Position: automatic, on the side (from medium screens), below the form |
| R2 | Width of the side chatter adjustable by dragging, limited to 20–65 % |
| R3 | Fold / unfold the chatter |
| R4 | Remembered per user; also in *My Preferences* |
| R5 | Company default position and width |
| R6 | Odoo 19 and 20 |

### 1.3 Scope (v1)

In: everything above.

Out:
- per-model layouts;
- chatter in a separate window (Odoo's attachment pop-out still works).

### 1.4 Acceptance criteria

- On a 1280 px screen, *On the side* shows form and chatter side by side.
- Dragging the left edge of the chatter changes its width; the width is kept after reloading.
- *Hide the chatter* leaves a thin *Show chatter* bar; one click opens it again.
- *Below the form* on a wide screen keeps the chatter below.

### 1.5 Screenshots

`static/description/screenshots/`: automatic, layout menu, on the side, wider, folded, preferences, settings.

---

## 2. Architecture

```
Server
  res.users: chatter_position / chatter_width / chatter_hidden   (empty → company default)
  ir.config_parameter: flexible_chatter.position / flexible_chatter.width
  ir.http.session_info() → session.flexible_chatter = {position, width, hidden}
  res.users.flexible_chatter_save(values)  ← chatter menu / drag / fold

Client
  chatter_prefs.js     reactive copy of the session value; CSS variable --o-flexible-chatter-width
  FormRenderer.mailLayout()  Odoo layout → mapped:  bottom: SIDE_CHATTER → BOTTOM_CHATTER
                                                     side (≥ LG): BOTTOM_CHATTER → SIDE_CHATTER
  Chatter: layout menu, mousedown on the left edge of .o-mail-Form-chatter.o-aside → width,
           folded bar (CSS hides the rest of the chatter)
  CSS: side by side below XXL (.o_form_renderer.flex-column:has(> .o-aside) → row)
```

### 2.1 Design decisions

- **One decision point**: Odoo's `mailLayout()` already chooses side / bottom; the module maps its result instead
  of rewriting the form compiler, so attachment previews keep working.
- **Width as a CSS variable on `<html>`**: dragging updates every chatter at once without re-rendering the form.
- **Changing the position re-renders the form** through Odoo's own resize handler (a `resize` event).
- **The drag handle is a pseudo-element** of the chatter container (outside OWL's DOM), detected on mousedown, so
  no foreign DOM is injected into Odoo's form.
- **Folding hides with CSS** (`:has()`), the chatter stays mounted and keeps its state.

---

## 3. Development

```
flexible_chatter/
├── models/
│   ├── res_users.py            preferences, effective layout, save from the client, width check
│   ├── ir_http.py              session info
│   └── res_config_settings.py  company default
├── views/                      preferences, settings
├── static/src/
│   ├── chatter_prefs.js        shared state, width variable
│   ├── form_renderer_patch.js  position
│   ├── chatter_patch.js/.xml   menu, drag, fold
│   └── flexible_chatter.scss
├── static/tests/tours/
└── tests/test_flexible_chatter.py
```

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 flexible_chatter
tools/run_tests.sh 20.0 /path/to/odoo20 flexible_chatter
```

| Test | Covers |
| --- | --- |
| `test_prefs_and_defaults` | defaults, company default, user choice |
| `test_save_from_the_chatter` | position, width clamped, fold, invalid position, preferences write, width check |
| `test_settings` | company default saved |
| `test_session_info` | layout sent to the client |
| `test_tour` | automatic → side → fold → open → below, saved for the user |

Results: 19.0 — 5 tests, 20.0 — 5 module tests (7 with Odoo's web suites), all green. Dragging is checked in the
screenshots run (the width changes and is saved).

**Manual test**
1. On a laptop-size window, open a contact, *On the side*; drag the left edge of the chatter.
2. *Hide the chatter*, reload, *Show chatter*.
3. *Below the form* on a wide screen.

---

## 5. Deployment: dev → staging → production

1. **Dev:** run the tests.
2. **Staging:** install, try the main forms (contacts, sales, tasks, tickets) on the screen sizes used in the
   company; set the company default.
3. **Production:** install, set the default; users adjust with the chatter menu.
4. **Performance:** no extra request when opening a form; one small write when the user changes the layout.
5. **Rollback:** uninstalling restores Odoo's layout; the user fields are dropped.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Chatter class | `@mail/chatter/web_portal/chatter` | `@mail/chatter/web_portal_project/chatter` |
| Shared state | `reactive()` + `useState()` | `proxy()` (read in templates through `this.`) |
| Document listener | `useExternalListener` | `useListener` |
| Root element | `this.rootRef.el` | `this.rootRef()` (signal ref) |
| Breakpoints | `@web/core/ui/ui_service` | `@web/core/ui/ui_utils` |
| User self-write | `SELF_*_FIELDS` | `user_writeable=True` |
| Icons | Font Awesome | Odoo icons |

---

## 7. Known limitations

- *On the side* needs at least a medium screen (992 px); below, the chatter stays below the form.
- The width is a percentage of the page, the same for all forms.
- Dragging needs a mouse (no touch drag on tablets; use the menu's default width).
