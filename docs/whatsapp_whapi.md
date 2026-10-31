# WhatsApp through Whapi.Cloud (`whatsapp_whapi`)

A **WhatsApp inbox inside Odoo 19.0 / 20.0**, connected through the Whapi.Cloud gateway:
- live chats and groups;
- media, voice notes, replies, forwards, stars, deletes, read ticks;
- templates and *Send by WhatsApp* on any document;
- a sandbox mode for non-production databases.

The code lives in:
- `19.0/whatsapp_whapi/`;
- `20.0/whatsapp_whapi/`.

---

## 1. Planning

### 1.1 Goal

Sales and support teams answer customers on WhatsApp from their own phones; nothing ends up in Odoo and only
the phone holder sees the conversation. The module brings the number into Odoo: everyone allowed sees the same
inbox, messages are linked to contacts and documents, and quotations or invoices can be sent in two clicks.

Whapi.Cloud links a normal WhatsApp (or WhatsApp Business app) number like WhatsApp Web does. No Meta business
verification or template approval is needed, unlike the official Cloud API (Odoo Enterprise `whatsapp`).

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | Connect one or more numbers: token, QR linking, connection status, webhook |
| R2 | Live inbox: chats and groups, search, unread, new messages without reload, notifications |
| R3 | Send and receive text, pictures, video, audio, voice notes and documents |
| R4 | Reply, forward to many chats, star, delete for everyone, message info with read receipts |
| R5 | Groups: participants, admins, add / remove / promote / demote, media, starred, event log |
| R6 | Contacts matched by phone; WhatsApp history visible on the contact |
| R7 | Templates with placeholders and PDF; *Send by WhatsApp* on any model |
| R8 | Access: who uses which number; token visible to administrators only |
| R9 | Safe in development and staging (no real messages) |
| R10 | Odoo 19 and 20, Community |

### 1.3 Scope (v1)

In: everything above.

Out:
- WhatsApp Channels / Newsletters and Status (stories): skipped by the webhook;
- reactions (ignored), polls, product catalogues and interactive buttons (stored as *Other* when received);
- calls;
- push notifications through Firebase (Odoo's own bus and the browser Notification API are used instead).

### 1.4 Roles

| Role | Can |
| --- | --- |
| *WhatsApp / User* | Chat on the accounts they are allowed on (all accounts when *Allowed users* is empty), send documents, read templates |
| *WhatsApp / Administrator* | Accounts (token, QR, webhook), templates, every chat of their companies |
| Public (Whapi.Cloud) | Only `POST /whapi/webhook/<account>/<secret>` |

### 1.5 Acceptance criteria

- A customer message reaches the open inbox within a second, with a pop-up when another chat is open.
- A reply with two pictures sends two messages; the first carries the text; both are quoted to the original.
- Ticks follow the statuses and never go back (a late *delivered* after *read* is ignored).
- In a group, a message is *read* only when every participant has read it; *Info* lists who has not.
- A webhook with a wrong secret is refused (403) and creates nothing.
- A user not allowed on an account sees neither the account nor its chats.

### 1.6 Screenshots

`static/description/screenshots/` in each version: inbox, group info, message actions, forward, message info,
emoji and templates, messages kanban, failed message, account, webhook, template, contact, composer, chats list.

---

## 2. Architecture

```
                 Whapi.Cloud ── POST /whapi/webhook/<account>/<secret> ──► controllers/main.py
                     ▲                                                        │ consteq(secret)
                     │ HTTPS (Bearer token)                                   ▼
whapi.account._whapi_request() ◄──────────────┐          whapi.account._whapi_process_webhook()
   (sandbox: fake answers)                    │            ├─ messages → whapi.message._whapi_from_webhook()
                                              │            │     chat (created), partner, media download,
whapi.message._whapi_send()  ─────────────────┘            │     reply link, edit / delete actions
   text / image / video / audio / voice / document         ├─ statuses → _whapi_status_from_webhook()
   forward: POST /messages/{id}                             │     ticks, per-participant receipts in groups
   delete:  DELETE /messages/{id}                           └─ groups / groups_participants → participants, log
                     │                                                        │
                     └──────────── _whapi_after_post() ◄──────────────────────┘
                                    last message, unread, contact chatter, document chatter
                                    └─ whapi.chat._whapi_notify() → bus "whapi/update" → inbox (OWL)
```

### 2.1 Design decisions

- **One HTTP entry point.** `whapi.account._whapi_request()` is the only place that talks to Whapi.Cloud. The
  sandbox mode and the tests replace it; errors become `UserError`s with the gateway's message.
- **One Odoo message per WhatsApp message.** Several files are sent as several messages (WhatsApp has no
  multi-file message); the inbox groups consecutive pictures into an album.
- **Media** go out as data URLs (`data:<mime>;name=<file>;base64,…`) and come in through `GET /media/{id}`,
  stored as attachments of the message (access follows the message). When the download fails but Whapi gives a
  link, a URL attachment is stored.
- **Statuses only move forward** (`draft < sent < delivered < read`). In groups each participant has a receipt
  line and the message is *read* when all of them have read it.
- **Live updates** use Odoo's bus on the partner of every allowed user (`whapi/update`), so no extra service is
  needed. The inbox reloads only what changed.
- **Phone matching** works on digits: `+32 471 …`, `0032 471 …`, and national `0471 …` completed with the
  contact's (or company's) country code.
- **Templates** reuse Odoo's `mail.render.mixin` (inline templates, same syntax and sandbox as e-mail templates).
- **Security**: webhook secret per account compared with `consteq`, regenerable; token restricted to
  administrators; record rules by allowed users and companies.

---

## 3. Development

```
whatsapp_whapi/
├── models/
│   ├── whapi_account.py     channel, HTTP, sandbox, QR, webhook, sync, webhook dispatch, phone helpers
│   ├── whapi_chat.py        chats, participants, group log, inbox data, group management, bus
│   ├── whapi_message.py     messages, sending, receiving, statuses, forward / star / delete, receipts
│   ├── whapi_template.py    templates + Action menu binding
│   └── res_partner.py       smart button, chat lookup, Send by WhatsApp
├── wizard/whapi_composer.py Send by WhatsApp (one or many records, PDF)
├── controllers/main.py      webhook
├── views/, security/, data/ backend views, groups and rules, hourly connection check
├── static/src/chat/         inbox (OWL), styles
├── static/tests/tours/      browser tour
└── tests/test_whapi.py      13 tests with a fake Whapi.Cloud
```

**Try it in a shell (sandbox, no phone needed)**

```python
account = env['whapi.account'].create({'name': 'Dev', 'sandbox': True})
anna = env['res.partner'].create({'name': 'Anna', 'phone': '+32 471 11 11 11'})
chat = anna._whapi_get_chat(account)
chat.whapi_send('Hello from Odoo')
# simulate an incoming message as Whapi.Cloud would post it
account._whapi_process_webhook({'messages': [{'id': 'X1', 'chat_id': chat.wa_id, 'type': 'text',
                                               'from': '32471111111', 'text': {'body': 'Hi!'}}]})
chat.whapi_load_messages()['messages']
```

**Extend**
- A new incoming type: add it to `_whapi_parse_content()` (returns type, text, media).
- Something to do on every new message (assign a salesperson, create a lead…): override `_whapi_after_post()`.
- Another gateway: override `_whapi_request()` and the endpoint names in `_whapi_send()`.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 whatsapp_whapi
tools/run_tests.sh 20.0 /path/to/odoo20 whatsapp_whapi
```

`tests/test_whapi.py` patches `_whapi_request` with a fake that records the calls and answers like Whapi.Cloud.

| Test | Covers |
| --- | --- |
| `test_connection_qr_webhook_and_sync` | health, QR, webhook payload, chats and groups sync, partner matching |
| `test_send_text_and_media` | text / image / document payloads, caption, quote, states, chatter copy |
| `test_failed_send_and_retry` | gateway error, retry |
| `test_webhook_incoming_text_media_reply_and_security` | wrong secret (403), duplicates, media download, reply link, mark as read |
| `test_webhook_statuses_delete_edit_and_phone_echo` | ticks never go back, edit, delete, messages sent from the phone |
| `test_groups_events_receipts_and_admin_actions` | group receipts, participant events, add / remove / promote / demote, log |
| `test_forward_star_delete_and_blocked_chat` | phone formats, forward to many, star, delete, ignored chat |
| `test_sandbox_account` | no HTTP call, fake ids |
| `test_templates_composer_and_binding` | rendering, many records, missing phone, Action menu binding |
| `test_composer_from_record_attaches_report` | PDF attached and sent as a document |
| `test_access_rules` | allowed users, token hidden, non-WhatsApp user |
| `test_ui_data` | inbox data and paging |
| `test_tour` | open a chat, reply to a message in the browser |

**Manual test (real number)**
1. Create the account, link the phone, register the webhook (use a public URL, e.g. a tunnel in development).
2. From another phone: send text, a picture and a voice note; reply to one of yours; delete one.
3. In Odoo: answer with a file, forward a message to two chats, check ticks and *Info*.
4. In a group: add and remove a participant from Odoo and check the group log.

---

## 5. Deployment: dev → staging → production

1. **Dev:**
   - run the tests;
   - use **Sandbox** accounts, simulate incoming messages with `_whapi_process_webhook()`.
2. **Staging:**
   - a restored production database contains the production accounts: switch them to **Sandbox** (or archive
     them) right after the restore, so staging never answers real customers;
   - test with a separate Whapi.Cloud channel and a test phone, with its own webhook URL.
3. **Production:**
   - one account per number, *Allowed users* set per team;
   - link the phone, register the webhook (HTTPS, correct `web.base.url`, the route must not be blocked by a
     proxy or a `dbfilter`), synchronise chats;
   - keep the phone online and charged; Whapi.Cloud keeps the session but WhatsApp may unlink inactive devices.
4. **Performance:**
   - webhooks are processed synchronously (one or a few SQL inserts per message, plus the media download);
   - the inbox loads 60 messages at a time and 80 chats;
   - group participants are matched to contacts once, when they appear.
5. **Monitoring:**
   - account state (hourly check);
   - *Messages* filtered on *Failed*, with the error and *Retry*;
   - server log `Whapi webhook refused` (wrong secret or archived account).
6. **Secrets:** rotate the webhook secret with *New secret* then *Register webhook*; the token is only readable by
   administrators.
7. **Rollback:** archive the account (webhooks are refused) or uninstall the module (chats, messages and their
   attachments are deleted; WhatsApp itself keeps the history on the phone).

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Inbox | OWL 2 (`useState`, `useRef`, `useService('bus_service')`) | OWL 3 (`proxy`, `useProps`, `signal.ref()`, `BusPlugin`, `NotificationPlugin`) |
| Templates | `t-esc` | `t-out`, `this.` in expressions |
| Binary fields | `bytes` | `BinaryValue` (`bytes(attachment.raw)`) |
| Config parameters | `get_param()` | `get_str()` |
| Access rights | `ir.model.access.csv` + record rules | `ir.access.csv` |
| Icons | Font Awesome | Odoo 20 icon set |

---

## 7. Known limitations

- **Unofficial API.** Whapi.Cloud drives a linked WhatsApp session. WhatsApp may restrict numbers that send
  bulk or unsolicited messages: use it for conversations, not campaigns.
- **Voice notes** are recorded in the browser format (OGG/Opus in Firefox, WebM/Opus in Chrome); WhatsApp may
  show WebM recordings as audio files instead of voice notes.
- **Reactions and calls** are ignored; **polls, catalogues and buttons** are stored as *Other* messages.
- **History before installation** is not imported: *Synchronise chats* loads the chats and groups, not their old
  messages.
- **Star** is kept in Odoo only (not synchronised with the phone).
- **Webhook must be public.** Odoo instances behind a VPN need a reverse proxy rule for `/whapi/webhook/`.
