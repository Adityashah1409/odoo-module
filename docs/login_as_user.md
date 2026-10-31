# Login As Other User (`login_as_user`)

Lets support people **open Odoo as another user** in **Odoo 19.0 / 20.0**:
- see exactly the menus, records and buttons that user sees;
- reproduce a problem without asking for a password;
- come back in one click.

Every session has a reason, a time limit, a notification to the user and a line in an audit log.

The code lives in:
- `19.0/login_as_user/`;
- `20.0/login_as_user/`.

---

## 1. Planning

### 1.1 Goal

"I can't see the export button" is hard to answer from an administrator account, which sees everything.
Asking for the user's password is not acceptable. The module gives a controlled way to become that user for a
few minutes, and keeps a trace of it.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | Switch from the top bar, the user form or the user list; search users and see their access first |
| R2 | The session really is the other user's: same menus, record rules, access rights, home page (portal for portal users) |
| R3 | Always visible that you are someone else, with a one-click way back |
| R4 | Who may do it: a dedicated group; nobody opens the superuser; administrators only by administrators; portal users only if allowed; other companies only by administrators |
| R5 | Reason (optional or required), notification to the user, time limit |
| R6 | Audit log: who, as whom, why, when, how long, how it ended, from where |
| R7 | Switching from one user to another keeps the real person as the one checked and logged |
| R8 | Odoo 19 and 20 |

### 1.3 Scope (v1)

In:
- backend users and portal users;
- top bar pill, switch screen, user form button and list action;
- portal / website banner;
- settings, log with list / form / pivot, cleanup job.

Out:
- logging every action done during the session (Odoo's chatter and tracking already show the impersonated user
  as author; the log tells who was behind it and when);
- opening a session through the XML-RPC / JSON-2 API;
- two-factor confirmation before switching.

### 1.4 Roles

| Role | Can |
| --- | --- |
| *Login as other user: Allowed* | Open sessions as allowed users, see their own log lines |
| Administrator (*Settings*) | Same, plus administrators and users of other companies; sees the whole log; settings |
| Everyone else | Nothing (no icon, routes refused) |

### 1.5 Acceptance criteria

- Logging in as Sofia shows Sofia's apps only, and an RPC to a model she cannot read fails.
- *Back to Elena Duarte* returns to Elena with the same session cookie flow as a normal login (rotated id).
- A member who is not an administrator cannot open an administrator, the superuser or a portal user (when not
  allowed).
- After the time limit, the next request is Elena's again and the log says *Time limit reached*.
- Logging out while being Sofia closes the log with *Logged out*.

### 1.6 Screenshots

`static/description/screenshots/` in each version:

| File | Shows |
| --- | --- |
| `switch_screen.png` | Search, badges, access of the selected user, reason |
| `impersonating_inbox.png` | Sofia's inbox with the notification, red pill with countdown |
| `impersonating_contacts.png` | Working as Sofia |
| `user_form.png` | *Log in as* button and *Login As* smart button |
| `log_list.png`, `log_pivot.png`, `log_form.png` | Audit log |
| `settings.png` | Settings block |
| `portal_banner.png` | Portal page with the floating banner |

---

## 2. Architecture

```
Top bar pill / switch screen (OWL)
        │  orm: res.users.login_as_search()        → users, groups, badges, settings
        │  rpc: /login_as/start {user_id, reason}
        ▼
LoginAsController.login_as_start
        ├─ res.users._login_as_check(origin, target, reason)   all the rules
        ├─ login.as.log.create(...)                             audit line
        ├─ mail.thread.message_notify(...)                      "Someone logged in as you"
        ├─ session['login_as_origin'] = {uid, login, name, log_id, time}
        └─ _switch_session(target)   login, uid, context, session_token; session id rotated
        ▼
Web client reloads as the target ── ir.http.session_info()['login_as'] → pill, countdown
        │
        ├─ every request: ir.http._pre_dispatch() → time limit reached? end_login_as('timeout')
        ├─ /login_as/stop (pill) or /login_as/back (portal banner) → end_login_as('switch_back')
        └─ /web/session/logout → log closed 'logout'
```

### 2.1 Design decisions

- **The session is switched, not faked.** `uid`, `login`, `context` and `session_token` are set for the target
  and the session id is rotated, exactly like after a password login. Record rules, menus, portal redirects and
  the session check all work unchanged.
- **The real person lives in the session.** `login_as_origin` is the only state. All checks use it, so a chained
  switch (Sofia → Lucas) is checked against Elena's rights, and Elena is the one written in the log.
- **One place for the rules**: `res.users._login_as_check()`. The switch screen hides users the check would
  refuse, but the route always checks again.
- **Read-only routes.** Odoo serves many requests with a read-only cursor. Closing the log is a write, so:
  - the time-limit check raises `ReadOnlySqlTransaction` on a read-only cursor, and Odoo replays the request
    with a read/write cursor;
  - the log is written and flushed **before** the session is changed, so a replay finds the session as it was;
  - `/web/session/logout` uses a `readonly` callable: read/write only while logged in as someone else.
- **Time limit twice.** The server enforces it (`_pre_dispatch`); the pill counts down and switches back in the
  browser so the user is not surprised by data changing under them.
- **Log access by record rules** (19) / `ir.access` (20): members see their own lines, administrators all. Log
  lines are read-only; only administrators can delete them.

---

## 3. Development

```
login_as_user/
├── controllers/main.py           start / stop / back routes, logout override, session switch
├── models/
│   ├── res_users.py              rules, switch screen data, form actions, smart button count
│   ├── login_as_log.py           audit log, close, cleanup job
│   ├── ir_http.py                session_info, time limit
│   └── res_config_settings.py    settings
├── data/                         default settings, cron
├── security/                     group, access rights, log rules
├── views/                        log, user form, settings, portal banner
├── static/src/login_as/          systray pill, switch screen, styles
├── static/src/frontend/          portal banner style
├── static/tests/tours/           browser tour
└── tests/test_login_as.py        13 tests
```

**Try it in a shell**

```python
Users = env['res.users']
elena, sofia = env.ref('base.user_admin'), Users.search([('login', '=', 'sofia')])
Users._login_as_check(elena, sofia, 'Ticket 42')   # raises when not allowed
Users.with_user(elena).login_as_search('sof')
env['login.as.log'].search([], limit=5).read(['origin_user_id', 'target_user_id', 'duration', 'end_reason'])
```

**Extend**
- Another rule (for example "only users of my team"): override `_login_as_check()` and call `super()`.
- Another place to switch from: return `user.action_login_as()` from a button.
- Something to run on every switch: override `/login_as/start` or `_switch_session()` callers.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 login_as_user
tools/run_tests.sh 20.0 /path/to/odoo20 login_as_user
```

| Test | Covers |
| --- | --- |
| `test_start_and_switch_back` | uid switches, session info, the target's rights apply, back, log closed, stop twice |
| `test_target_is_notified` | message to the user with author and reason |
| `test_reason_required` | blank reason refused, then allowed when the setting is off |
| `test_permissions` | no group, yourself, administrator, superuser, public, portal, archived, feature off |
| `test_admin_can_log_in_as_admin_and_portal` | administrator rights, portal landing page |
| `test_chained_switch_keeps_the_real_user` | Sofia → Lucas → back to the real user, log reasons |
| `test_time_limit` | session older than the limit switches back (read-only replay), no limit |
| `test_logout_closes_the_log` | logout while impersonating |
| `test_frontend_banner` | banner on a frontend page, *Back* link |
| `test_search_and_session_info` | switch screen data, hidden users, `login_as.can` |
| `test_log_access_and_cron` | members see their own lines, admins all, smart button count, cleanup job |
| `test_user_form_action` | form actions |
| `test_tour` | systray → search → reason → log in → pill → back |

**Manual test**
1. Give *Login as other user: Allowed* to a non-admin user and log in with it.
2. Open the spy icon, pick a user, try without a reason, then with one.
3. Check the pill, the countdown, the user's inbox, and *Back to …*.
4. Try an administrator from the non-admin account: refused.
5. Allow portal users, open one: the portal shows the banner; use *Back*.

---

## 5. Deployment: dev → staging → production

1. **Dev:**
   - run the tests;
   - decide the settings: reason required, notification, portal users, time limit.
2. **Staging:**
   - restore a copy of production and install the module;
   - give the group to one support person and run the manual test;
   - check e-mail notifications go out (outgoing mail server) and are acceptable for your users.
3. **Production:**
   - install, then give the group only to the support team;
   - announce it internally: users receive a notification each time someone opens their account;
   - add the log to the security review (filter *As an administrator*, group by *Done by*).
4. **Performance:** one session dict lookup per request; one config read per request only while logged in as
   someone else. The cron runs hourly on an indexed state.
5. **Monitoring:**
   - *Login As Log* with the *Running* filter;
   - pivot: time spent per support person and user.
6. **Rollback:** uninstall the module. Running sessions as someone else keep the target user until they log
   out; log out those users or restart with a cleared session store if needed. The log is deleted with the
   module, so export it first if you need to keep it.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Session helpers | `request.session.logout()`, `odoo.http.SESSION_LIFETIME` | `odoo.http.session.logout(session)`, `odoo.http.session.SESSION_LIFETIME` |
| `/web/session/logout` | GET | POST with CSRF token |
| Settings values | `get_param()` strings | typed `get_bool()` / `get_int()` |
| Access rights and log rules | `ir.model.access.csv` + `ir.rule` | `ir.access.csv` |
| Web client | OWL 2 (`useState`, `static props`) | OWL 3 (`proxy`, `useProps`, `this.` in templates) |
| Icons | Font Awesome | Odoo 20 icon set |
| Discuss | inbox list | notifications tab (the notification opens in a dialog) |

---

## 7. Known limitations

- **Actions are done as the target.** Messages, tracking and created records show the target user as author.
  The log gives who was behind the session and when; it does not record each action.
- **Two-factor authentication** of the target is not asked (the session is opened by an already authenticated
  person); the origin's own 2FA applies at their login.
- **API access** (XML-RPC, JSON-2, API keys) is not covered: only browser sessions.
- **Session expiry.** When the browser is closed without logging out, the log line stays *Running* until the
  time limit (+ 1 hour) or Odoo's session lifetime (7 days), then the hourly job closes it.
- **Other sessions of the origin** (another browser) are not affected.
