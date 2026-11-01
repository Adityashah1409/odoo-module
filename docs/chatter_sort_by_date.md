# Chatter: Sort by Date (`chatter_sort_by_date`)

Oldest-first or newest-first chatter for **Odoo 19.0 / 20.0**, remembered per user with a company default.

The code lives in:
- `19.0/chatter_sort_by_date/`;
- `20.0/chatter_sort_by_date/`.

---

## 1. Planning

### 1.1 Goal

Odoo always shows the chatter newest first. To understand the history of a customer, a ticket or a project,
people want to read it as a story, from the first message down. Reversing only the loaded page is not enough:
the chatter loads the latest 30 messages, so "oldest first" must start at the real first message.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | Toggle *Newest first* / *Oldest first* in the chatter of every record |
| R2 | Oldest first starts at the first message of the record and loads newer ones on scroll |
| R3 | The choice is remembered per user, also in *My Preferences* |
| R4 | Company default for users without a choice |
| R5 | Discuss channels and the Inbox unchanged |
| R6 | Odoo 19 and 20 |

### 1.3 Scope (v1)

In: everything above.

Out:
- per-model order (one order for all records);
- the portal chatter (customers keep Odoo's order).

### 1.4 Acceptance criteria

- A record with 35 notes shows *Note 35* on top; after the toggle, *Note 01* on top; reloading keeps it.
- Scrolling down in oldest first reaches *Note 35*.
- With the company default *Oldest first*, a new user sees oldest first.

### 1.5 Screenshots

`static/description/screenshots/`: newest first, oldest first, oldest first scrolled to the end, preferences,
settings.

---

## 2. Architecture

```
Server
  res.users.chatter_message_order (user choice) ─┐
  ir.config_parameter chatter_sort_by_date.default_order ─┴─► _chatter_effective_order()
  ir.http.session_info() ──► session.chatter_message_order
  res.users.chatter_set_message_order(order)  ◄── toggle

Client
  Chatter.setup: state.chatterOrder = session value
  Chatter.changeThread: thread.chatterOldestFirst = (order == 'asc')
  <Thread order="state.chatterOrder"/>
  Thread.fetchNewMessages (first load) ──► chatterLoadOldest(): fetchMessages(after: -1)
        server: id > -1 ORDER BY id ASC LIMIT 30  →  first 30 messages, loadNewer = true
  scrolling down: Odoo's own "load newer" (fetchMoreMessages('newer'))
  toggle back: chatterLoadNewest(): reset, Odoo's normal newest-first load
```

### 2.1 Design decisions

- **Reuse Odoo's "load newer" machinery** (made for jumping to an old message): asking the server for messages
  after id -1 returns the first page in ascending order, and the Thread component then pages forward on scroll.
  No new route or server query.
- **Order in the session**, so the first render is already in the right order (no flicker).
- **User field + company default**: the field is empty until the user chooses.
- **Only record chatters** (`discuss.channel` and `mail.box` excluded).

---

## 3. Development

```
chatter_sort_by_date/
├── models/
│   ├── res_users.py            user choice, effective order, toggle method
│   ├── ir_http.py              session info
│   └── res_config_settings.py  company default
├── views/                      preferences, user form, settings
├── static/src/                 chatter toggle and thread order, oldest-first loading
├── static/tests/tours/         two tours
└── tests/test_chatter_order.py
```

**Extend**
- Per-model order: store a JSON of model → order on the user and read it in `changeThread`.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 chatter_sort_by_date
tools/run_tests.sh 20.0 /path/to/odoo20 chatter_sort_by_date
```

| Test | Covers |
| --- | --- |
| `test_effective_order_and_toggle` | user / company / fallback, toggle method, invalid value, preferences write |
| `test_settings` | company default saved |
| `test_session_info` | effective order sent to the client |
| `test_tour_toggle_and_remember` | 35 notes: newest first, toggle, first note on top, remembered, back |

Results: 19.0 — 4 tests, 20.0 — 4 module tests (6 with Odoo's web suites), all green.

**Manual test**
1. Open a record with many messages, click *Newest first* → *Oldest first*; scroll to the end.
2. Reload: the order is kept. Check *My Preferences*.

---

## 5. Deployment: dev → staging → production

1. **Dev:** run the tests.
2. **Staging:** install, try records with long chatters (> 30 messages), choose the company default.
3. **Production:** install, set the default; users switch with the toggle.
4. **Performance:** no extra query on newest first; oldest first uses the same paged queries as Odoo.
5. **Rollback:** uninstalling restores Odoo's order; the user field is dropped.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Chatter class | `@mail/chatter/web_portal/chatter` | `@mail/chatter/web_portal_project/chatter` |
| Template expressions | `state.chatterOrder` | `this.state.chatterOrder` (OWL 3) |
| Fetch API | `fetchMessages({after})` | `fetchMessages({fetchParams: {after, limit}})` |
| User self-write | `SELF_READABLE_FIELDS` / `SELF_WRITEABLE_FIELDS` | `user_writeable=True` on the field |
| Settings in code | `get_param` | `get_str` |
| Icons | Font Awesome sort icons | Odoo icons (arrows) |

---

## 7. Known limitations

- In oldest first, a message posted while older pages are shown appears once the end of the thread is loaded.
- The order is per user, not per model.
- The portal chatter keeps Odoo's order.
