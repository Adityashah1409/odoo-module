# Access Management

**Odoo 20.0** · LGPL-3 · Category: Administration

This module controls what each user or group can see and do, beyond Odoo's standard groups. You can:
- hide menus;
- lock models;
- hide, lock, require or mask fields;
- hide buttons, tabs, chatter controls, reports and actions;
- block export, import, archive and duplicate;
- limit the records a user sees with a domain;
- make a user read-only;
- schedule rules in time windows;
- track exports;
- protect menus with a PIN.

It also includes an access map and a dashboard.

![Dashboard](static/description/screenshots/dashboard.png)

## Features

- **Access rules for users or groups.**
  - A rule applies to selected users, or to all members of selected groups (implied groups included).
  - You can exclude users and limit a rule to some companies.
  - A rule can have start and end dates, and a weekly window (days, hours, timezone).
  - The rule form shows whether it is applying right now. A scheduled action keeps that status up to date
    every 5 minutes.
- **Menus.**
  - Hide any menu, submenu or whole app.
  - Opening a hidden menu's action by URL is refused too (optional).
  - An access manager can never be locked out of this module.
- **Models.**
  - Operations: no create, edit, delete, duplicate, archive, import or export, or the *Read-only* shortcut.
  - **Record domain**: users only see and change matching records, for example `[('user_id', '=', user.id)]`.
    The domain is enforced on the server, for every read and write.
- **Fields.**
  - Hide a field, make it read-only, or make it required.
  - **Mask** text fields, keeping the first and last characters visible. E-mails keep their shape. The masked
    value is what the browser receives. Formatted copies of the field (for example `phone_formatted`) are
    masked too.
  - A mask can apply only to records that match a domain.
  - Masked and hidden fields cannot be exported. Read-only fields cannot be changed through the web client or
    a JSON-RPC `write`.
- **Buttons and tabs.**
  - Hide buttons by technical name, including smart buttons.
  - Calling a hidden button through `/web/dataset/call_button` is refused.
  - Hide notebook pages.
  - Each line lists the names found in the model's views.
- **Chatter.**
  - Hide the whole chatter, or only *Send message*, *Log note*, activities, followers or attachments.
  - Posting from the chatter and scheduling activities are refused on the server too.
- **Print and Action menus.** Hide all reports or some, and all bound actions or wizards or some. The report
  URL is refused as well.
- **Search.** Hide filters, group-bys or the search panel.
- **User-level options.**
  - *Read-only user*: no create, write or delete on business models.
  - *Disable developer mode*.
  - *Block external API*: XML-RPC / JSON-RPC logins and API keys are refused.
  - *Block login*: combine it with a weekly window, for example no logins at night.
- **PIN-protected menus.**
  - A menu asks for a numeric PIN or a passphrase before it opens, even from a bookmarked URL.
  - The lock can apply to everyone, or only to chosen users or groups.
  - Settings: number of attempts, lockout time, how long the menu stays unlocked, and alert e-mails.
  - Codes are stored as salted PBKDF2 hashes, and every attempt is logged.
- **Export tracking.**
  - Every export is logged: user, model, number of records, columns, IP address.
  - When an export is larger than a threshold, a leak alert is e-mailed.
  - Old logs are cleaned up automatically.
- **Access map.**
  - For any user, a table of read, write, create and delete rights on every model: *Yes*, *Limited* (by
    record rules) or *No*.
  - The table is grouped by application and flags the models that a rule changes.
  - It can be downloaded as a colour-coded Excel file.
- **Export / import rules as JSON.** Move rules from staging to production. A dry run reports what would be
  created, updated, skipped or would fail.
- **Dashboard.**
  - Counters: active, applying and expired rules, restricted users, exports and leak alerts, wrong PINs.
  - Rules table, restriction types, most restricted models, records exported per day, recent exports and the
    users with the most rules.
  - Quick actions: *New rule*, *Archive expired*, *Refresh caches*, *Access map*.
- **Access rules** smart button on users.

## Screenshots

| | |
| --- | --- |
| **Dashboard**<br>![Dashboard](static/description/screenshots/dashboard.png) | **Rules**<br>![Rules](static/description/screenshots/rules_list.png) |
| **Rule: who, when, hidden menus**<br>![Rule](static/description/screenshots/rule_form.png) | **Rule: models**<br>![Models](static/description/screenshots/rule_models.png) |
| **Model restrictions**<br>![Model line](static/description/screenshots/rule_model_line.png) | **Rule: fields (masks with preview)**<br>![Fields](static/description/screenshots/rule_fields.png) |
| **Rule: buttons and tabs**<br>![Elements](static/description/screenshots/rule_elements.png) | **Weekly window: no login at night**<br>![Schedule](static/description/screenshots/rule_schedule.png) |
| **PIN-protected menu**<br>![Lock](static/description/screenshots/menu_lock.png) | **PIN prompt (wrong code)**<br>![PIN](static/description/screenshots/max_pin.png) |
| **Salesperson: masked e-mail and phone, no Notes tab, no Log note**<br>![Contact](static/description/screenshots/sarah_contact.png) | **Salesperson: no Export, Delete or Archive**<br>![Actions](static/description/screenshots/sarah_contacts_actions.png) |
| **Salesperson: order without Cancel or attachments**<br>![Order](static/description/screenshots/sarah_order.png) | **Salesperson: CRM without Reporting**<br>![CRM](static/description/screenshots/sarah_crm.png) |
| **Read-only intern**<br>![Read-only](static/description/screenshots/max_readonly.png) | **Access map**<br>![Map](static/description/screenshots/access_map.png) |
| **Export log with a leak alert**<br>![Exports](static/description/screenshots/export_log.png) | **Import rules: dry run**<br>![Transfer](static/description/screenshots/transfer.png) |
| **Settings**<br>![Settings](static/description/screenshots/settings.png) | **Access rules on a user**<br>![User](static/description/screenshots/user_form.png) |

## Installation

Add `20.0/` of this repository to your addons path and install **Access Management**.
- **Odoo dependencies**: `mail`.
- **Python**: nothing extra. The Excel export uses `xlsxwriter`, which Odoo already ships.

## Configuration

1. Give the **Access Management / Manager** group to the people who set up rules. Settings administrators get
   it automatically.
2. Open *Access Management › Access Rules › New*:
   - choose users or groups (and exceptions);
   - set the dates or a weekly window if needed;
   - fill the tabs (*Menus*, *Models*, *Fields*, *Buttons and tabs*, *User restrictions*).
3. Click *Apply now*. Users get the change at their next page load.
4. Optional: in *PIN-protected Menus*, add a menu and set its code.
5. Optional: in *Configuration › Settings*, set the leak-alert threshold and recipients and the log retention.

## Technical overview

| Part | Role |
| --- | --- |
| `access.rule` (+ `access.rule.model`, `.field`, `.element`) | Rules and their lines. `_restrictions_for(uid, company)` builds and caches the restrictions of a user; `_restriction_domain` adds the security domain |
| `base._access_domain` | Record restrictions, read-only users and blocked operations, enforced by the ORM |
| `base` (`get_view`, `get_views`, `fields_get`, `web_read`, `web_save`, `export_data`, `load`, `copy`, archive) | View changes, toolbar filtering, masking, export and import checks |
| `ir.ui.menu._visible_menu_ids` | Hidden menus |
| `ir.http._handle_debug`, `res.users._check_credentials`, `res.users.apikeys._check_credentials` | Developer mode, login and API blocking |
| `mail.thread.message_post`, `mail.activity.create` | Chatter enforcement |
| `controllers/main.py` | `/web/action/load` (hidden menus, PIN prompt), `call_button`, report routes, `/access_management/unlock` |
| `access.menu.lock`, `access.lock.attempt` | PIN locks and attempts |
| `access.export.log` | Export log and leak alerts |
| `access.map`, `access.rule.transfer` | Access map and rule import / export |
| `static/src/` | Dashboard, PIN prompt, list export patch, chatter styles |

## Odoo 20 notes

- Odoo 20 merged `ir.model.access` and `ir.rule` into `ir.access`. Each model now computes its security domain
  in `_access_domain`, so the restrictions are added there.
- Settings use the typed getters (`get_int`, `get_str`).
- Access rights are in `ir.access.csv`.
- The dashboard and the PIN prompt use OWL 3:
  - `useProps(standardActionServiceProps)`;
  - `signal.ref()`;
  - `proxy`;
  - `this.` in templates;
  - no `t-model`.
- Binary fields are written as base64 strings and read as `BinaryValue`.
- Masking also covers the formatted copies of a field. For example, the phone widget in Odoo 20 displays
  `phone_formatted`.

## Tests

```bash
tools/run_tests.sh 20.0 /path/to/odoo20 access_management
```

There are 33 tests:
- **Rules**:
  - who a rule applies to;
  - dates and weekly windows (frozen time);
  - blocked operations and the read-only shortcut;
  - record domains (`user`);
  - read-only users;
  - hidden menus and their actions, and the manager exemption;
  - login and API blocking (including API keys);
  - exempt models.
- **User interface**:
  - view flags;
  - hidden, read-only, required and masked fields, including companions, export and `web_save`;
  - mask domains;
  - tabs and buttons;
  - chatter and activities;
  - toolbar actions;
  - search view;
  - archive, import and export;
  - x2many sub-views.
- **Tools**:
  - export log merging, leak alert and retention;
  - PIN hashing, attempts, lockout and alert;
  - access map and Excel file;
  - JSON export and import (dry run, create, skip, update, warnings);
  - dashboard.
- **HTTP**:
  - PIN prompt and unlock;
  - hidden-menu action refused;
  - hidden button, duplicate and read-only field refused over RPC;
  - chatter posting;
  - developer mode;
  - report route;
  - 2 browser tours (dashboard; PIN unlock, then Export missing from the action menu).

## Full guide

[docs/access_management.md](../../docs/access_management.md) · Odoo 19.0: [`19.0/access_management`](../../19.0/access_management)

---
Author: Aditya Shah · License: LGPL-3
