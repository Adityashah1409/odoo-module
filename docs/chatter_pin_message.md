# Chatter: Pin Messages (`chatter_pin_message`)

Pinned messages in the chatter of any record for **Odoo 19.0 / 20.0**:
- 19.0: the whole feature (pin action, pinned bar, rules, who pinned, overview);
- 20.0: Odoo pins chatter messages natively, the module adds the rules, who pinned and the overview.

The code lives in:
- `19.0/chatter_pin_message/`;
- `20.0/chatter_pin_message/`.

---

## 1. Planning

### 1.1 Goal

Important facts about a customer or a document get lost in a long chatter: delivery windows, payment rules,
"PO number mandatory on invoices". Teams need them on top, visible to everyone opening the record, with control
over who can pin and how many pins are allowed so the list stays meaningful.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | Pin / unpin messages and notes in the chatter of any record (`mail.thread`) |
| R2 | Pinned messages visible on top of the chatter, with jump to the message |
| R3 | Who pinned and when |
| R4 | Rules: who can pin (edit or read right), maximum pins per record, only messages and notes, internal users only |
| R5 | Pinning must not modify the message (write date, notifications) |
| R6 | Overview of all pinned messages across records |
| R7 | Odoo 19 and 20 (20 already has the basic pin feature in the chatter) |

### 1.3 Scope (v1)

In: everything above.

Out:
- pin expiry dates;
- pins visible in the customer portal;
- per-model rules (one rule for all records).

### 1.4 Acceptance criteria

- Pinning a note on a contact shows *1 pinned message* on top of its chatter and a pin icon on the message (19).
- *Jump* scrolls to an old pinned message that was not loaded yet (19).
- With *Pins per record = 3*, pinning a fourth message shows *"This record already has 3 pinned messages. Unpin
  one first."*
- An employee who can only read a record cannot pin unless *Who can pin = Everyone who can see the record*.
- *Discuss › Pinned* lists the pin with who pinned it.

### 1.5 Screenshots

`static/description/screenshots/`:
- 19.0: pinned bar collapsed and open, pin action, jump, limit, overview, settings;
- 20.0: Odoo's pinned panel, pin action, limit, overview, settings.

---

## 2. Architecture

```
19.0
  Message action "chatter-pin" ──► Thread.chatterTogglePin(message)
                                     └─ orm.call(model, "chatter_set_message_pin", [id], {message_id, pinned})
  ChatterPinnedBar (in mail.Chatter) ─► Thread.fetchChatterPins() ─► orm.call(model, "chatter_pinned_messages")
                                          └─ store.insert(messages) + chatterPinInfo {message id: who / when}
  mail.thread.chatter_set_message_pin
     ├─ _chatter_pin_check_rights(): internal user, check_access('write' | 'read')
     ├─ message of this record, type comment / email, limit
     └─ SQL UPDATE pinned_at, pinned_by_id   (no write date change)

20.0
  Odoo's message action "Pin" / panel "Pinned Messages" ─► mail.thread.set_message_pin (Odoo)
  override: rules first (records only, channels untouched) ─► super() ─► SQL pinned_by_id

Both: mail.message.pinned_by_id, settings in ir.config_parameter, action "Pinned" (mail.message list)
```

### 2.1 Design decisions

- **Reuse `mail.message.pinned_at`**: the field already exists for channel pins; the same field serves chatter
  pins, so the 19 data is ready for Odoo 20's native panel after an upgrade.
- **SQL update** like Odoo's own pin: no write date change, no write right needed on the message itself.
- **Rights on the document, not on the message**: by default pinning needs the right to edit the record, because a
  pin changes what every user sees first.
- **19 bar computes its own order**: Odoo 19's `pinnedMessages` field (made for channels) never settles its sort
  when two pins share the same second, which froze the page. The bar sorts by `pinned_at` then id itself; the
  browser tour pins two messages in the same second to keep this covered.
- **20 keeps Odoo's UI**: no duplicate panel; the module only adds what Odoo lacks.

---

## 3. Development

```
chatter_pin_message/
├── models/
│   ├── mail_message.py          pinned_by_id
│   ├── mail_thread.py           rules + pin (19: own methods, 20: set_message_pin override)
│   └── res_config_settings.py   who can pin, pins per record
├── views/                       overview list + search, settings
├── static/src/ (19 only)        message action, thread patch, pinned bar, pin icon
├── static/tests/tours/ (19)     browser tour
└── tests/test_pin.py
```

**Try it in a shell**

```python
partner = env['res.partner'].browse(9)
msg = partner.message_post(body='Delivery: Tuesdays 8-10 only', subtype_xmlid='mail.mt_note')
partner.chatter_set_message_pin(msg.id, True)   # 19.0
partner.set_message_pin(msg.id, True)           # 20.0
msg.pinned_by_id
```

**Extend**
- Per-model rules: override `_chatter_pin_check_rights()` in the model.
- Other pinnable message types: `PINNABLE_TYPES` in `models/mail_thread.py`.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 chatter_pin_message
tools/run_tests.sh 20.0 /path/to/odoo20 chatter_pin_message
```

| Test | Covers |
| --- | --- |
| `test_pin_and_unpin` | pin, who pinned, write date unchanged, pin twice, unpin |
| `test_wrong_messages` | message of another record, tracking message |
| `test_limit` | limit reached, 0 = no limit |
| `test_access` | edit right needed by default, read right when allowed, portal refused |
| `test_overview` | overview domain, *Open* button |
| `test_settings` | settings saved in system parameters |
| `test_tour` (19) | browser: pin action, icon, bar count, who pinned, jump, unpin, same-second pins |
| `test_channel_pins_untouched` (20) | channels: no limit, who pinned stored |

Results: 19.0 — 7 tests, 20.0 — 7 module tests (9 with Odoo's web suites), all green.

**Manual test**
1. Open a contact with a few notes, pin two of them (19: message action *Pin*; 20: *Pin*).
2. 19: open the pinned bar, *Jump*, *Unpin*. 20: open *Pinned Messages* in the chatter top bar.
3. Set *Pins per record* to 1 and pin another: the limit message appears.
4. Log in as an employee without edit right on the record: pinning is refused.

---

## 5. Deployment: dev → staging → production

1. **Dev:** run the tests; agree on who can pin and the limit.
2. **Staging:** install, set the rules, pin a few messages on real records; on 19 check the bar on the main
   models (contacts, sales, tasks, tickets).
3. **Production:** install (no data migration: existing messages are untouched), set the rules.
4. **Upgrade 19 → 20:** pins are kept (`pinned_at`, `pinned_by_id`) and appear in Odoo 20's *Pinned Messages*
   panel.
5. **Performance:** one extra indexed-by-thread query per opened chatter (19), none in 20.
6. **Rollback:** uninstalling drops *who pinned*; `pinned_at` belongs to Odoo and stays (on 19 the pins are then
   only visible in the database).

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Pin in the chatter | added by the module (message action *Pin*) | native (*Pin* / *Unpin* actions) |
| Pinned list in the chatter | module's pinned bar on top, with who pinned | native *Pinned Messages* panel |
| Backend entry point | `chatter_set_message_pin()` / `chatter_pinned_messages()` | override of native `set_message_pin()` |
| Pinned icon on messages | added by the module | — |
| Rules, limit, who pinned, overview | module | module |
| Settings access in code | `get_param()` | `get_str()` / `get_int()` |
| Access test helper | `ir.rule` | `ir.access` (rules in CSV); tests use an employee without *Contact Creation* |

---

## 7. Known limitations

- Other users see a new pin after reloading the record (no live update).
- The limit counts pins per record, whatever their author.
- 20: Odoo's own panel does not show who pinned; it is in the *Pinned* overview.
