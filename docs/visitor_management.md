# Visitor Management (`visitor_management`)

Front desk for **Odoo 19.0 / 20.0**:
- expected visits and invitations with a pass code;
- check-in / check-out at the reception or on a self-service kiosk;
- host notification, visitor pass, reporting.

The code lives in:
- `19.0/visitor_management/`;
- `20.0/visitor_management/`.

---

## 1. Planning

### 1.1 Goal

Reception teams keep paper visitor books or spreadsheets: nobody knows who is still in the building, hosts are
called by phone, and there is no history. Odoo Community has no front-desk app. This module adds one on top of
Employees, so hosts, departments and notifications come for free.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | A visit with visitor details, host employee, type, category, destination, expected date, check-in / check-out and time on site |
| R2 | Flow *Expected* → *On site* → *Checked out* / *Cancelled*, from the form, the kanban card or the list |
| R3 | The host is told at check-in (inbox or e-mail); can be turned off |
| R4 | Invitation e-mail with a unique, easy-to-type pass code |
| R5 | Public kiosk: invited visitors check in with the code, walk-ins with a form, everyone checks out with the code |
| R6 | Printable pass with a QR code; escort and overstay warnings |
| R7 | Automatic check-out of forgotten visitors; reporting by department, host, type |
| R8 | Receptionist / Administrator roles, multi-company; Odoo 19 and 20 |

### 1.3 Scope (v1)

In: everything above.

Out:
- ID document scans and NDA signatures (privacy and legal review needed first);
- badge printers (the A6 PDF prints on any printer);
- SMS / WhatsApp notifications (the host's notification preference decides inbox or e-mail);
- QR scanning at the kiosk (the code is typed; the QR is for a later scanner integration).

### 1.4 Acceptance criteria

- An expected visit gets `VIS/2026/0001` and a 6-character code without 0/O/1/I.
- *Check in* puts it *On site* and the host gets *"Nora Vermeulen (Delta Logistics) has arrived and is waiting
  for you at Room Atlas."*
- *Check out* 1h30 later shows 01:30 on site.
- At the kiosk, the invited visitor's code checks them in; a walk-in without host gets an error and keeps what
  they typed; the check-out with the code says goodbye.
- A visitor still on site after 10 hours is checked out by the scheduled action and flagged.
- An employee without the Visitors role cannot read visits.

### 1.5 Screenshots

`static/description/screenshots/` in each version:
- kanban, list, expected visit, invitation, escort, overstay;
- kiosk home, check-in, welcome (walk-in and invited), check-out, goodbye;
- host notification, pass, calendar, graph, pivot, employee, visit types, settings.

---

## 2. Architecture

```
Reception (backend)                       Kiosk (public, /visitor/kiosk/<token>)
  visitor.visit form / kanban / list        controllers/kiosk.py
    action_check_in ─┐                        ├─ token → res.company (consteq)
    action_check_out │                        ├─ check-in:  _kiosk_check_in(company, post)
    action_send_invitation (composer)         │      pass code → planned visit → action_check_in
    action_print_pass (A6 report, QR)         │      walk-in   → create(source=kiosk) → action_check_in
                     ▼                        └─ check-out: _kiosk_check_out(company, code)
              _notify_host()  ── message_post(partner_ids = host.work_contact_id, author = user or company)

ir.cron (hourly) ── _cron_auto_check_out(): on_site and check_in < now - company.visitor_max_hours
hr.employee ── visitor_kiosk_host, visitor_visit_count (smart button)
res.company ── visitor_kiosk_token, visitor_notify_host, visitor_max_hours, visitor_kiosk_message
```

### 2.1 Design decisions

- **Host = employee**, not user: every employee can receive visitors; the notification goes to the employee's
  *work contact*, so users get it in their inbox and others by e-mail.
- **Receptionists do not need HR rights**: the host is read through Odoo's public employee profile; the
  department is a stored related field computed as superuser.
- **The kiosk is a plain HTTP page** (`web.frontend_layout`, no `website` dependency) behind a secret link per
  company. All writes go through two model methods that validate every input (host must be offered on the kiosk,
  visit type must be offered on the kiosk, lengths capped).
- **Pass codes** use an alphabet without look-alike characters and are unique in the database (SQL constraint);
  the kiosk accepts lower case and spaces.
- **Kiosk notifications** are posted in the company's name, not as the public user.
- **Overstay** is computed live (not stored), from the visit type's usual duration.

---

## 3. Development

```
visitor_management/
├── models/
│   ├── visitor_visit.py         visit: flow, pass code, notification, invitation, pass QR, cron, kiosk
│   ├── visitor_config.py        visit types, categories, destinations
│   ├── hr_employee.py           kiosk option, visits smart button
│   ├── res_company.py           kiosk token and options
│   └── res_config_settings.py   settings, new kiosk link
├── controllers/kiosk.py         public kiosk pages
├── data/                        sequence, cron, types, categories, invitation template, demo
├── report/                      A6 visitor pass
├── security/                    Receptionist / Administrator, company rules
├── views/                       visits, configuration, employee, settings, kiosk templates, menus
├── static/src/scss/kiosk.scss   kiosk look
└── tests/test_visitor.py        10 unit tests + 1 HTTP test of the kiosk
```

**Try it in a shell**

```python
visit = env['visitor.visit'].create({'visitor_name': 'Nora', 'host_id': env.ref('hr.employee_admin').id})
visit.pass_code                    # 'K7M2QX'
visit.action_check_in()            # host notified
visit.action_check_out()
visit.duration                     # hours on site
env.company._visitor_kiosk_url()   # link for the tablet
```

**Extend**
- More visitor fields: add them to the model, the form and `_kiosk_check_in()` (with the template input).
- Another notification channel: override `_notify_host()`.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 visitor_management
tools/run_tests.sh 20.0 /path/to/odoo20 visitor_management
```

| Test | Covers |
| --- | --- |
| `test_create_reference_and_pass_code` | sequence, code format and uniqueness, department from the host |
| `test_check_in_notifies_host_and_check_out` | notification body and recipient, duration, wrong transitions |
| `test_no_notification_when_disabled` | company option |
| `test_cancel_and_reset` | cancel / reset from expected and on site |
| `test_overstay_and_auto_check_out` | usual duration, cron with limit, 0 = never |
| `test_partner_onchange_and_invitation` | contact onchange, composer with the template, mail sent, flag |
| `test_check_out_before_check_in_refused` | date constraint |
| `test_access_rights` | receptionist vs administrator, employees without the role, public host profile |
| `test_pass_report` | QR, code, escort line |
| `test_kiosk_methods` | pass code (case, spaces), walk-in, hidden host and type, check-out, errors |
| `test_kiosk_pages` (HTTP) | wrong token 404, pages, CSRF forms, kept input on error, company as author |

Results: all 11 module tests green on 19.0 and 20.0 (the 20.0 run also counts Odoo's two web JS suites).

**Manual test**
1. Give yourself the *Administrator* role; open *Visitors › Configuration › Settings*, copy the kiosk link.
2. Create an expected visit with your e-mail, *Send invitation*.
3. Open the kiosk link in a private window: check in with the code, then as a walk-in, then check out.
4. Check the host's inbox, print the pass, look at *Reporting*.

---

## 5. Deployment: dev → staging → production

1. **Dev:** run the tests; agree on visit types, categories and destinations with the reception.
2. **Staging:**
   - install; set the roles; untick employees who should not appear on the kiosk;
   - check outgoing mail (invitations, host e-mails) and the invitation wording;
   - test the kiosk link on the real tablet (full-screen browser / kiosk mode).
3. **Production:**
   - install, configure, then **generate a new kiosk link** so the staging link does not work on production;
   - put the tablet browser in kiosk mode on the link; the pages need no login;
   - print a test pass on the reception printer (A6).
4. **Performance:** one record per visit; `state`, `pass_code` and `department_id` are indexed or stored; the cron
   searches on-site visits only.
5. **Security:** the kiosk link is the only secret: renew it when a tablet is lost. Kiosk forms are CSRF-protected
   and only create visits for the token's company.
6. **Rollback:** uninstalling removes visits and configuration; employees are unchanged.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Access rights and record rules | `ir.model.access.csv` + `ir.rule` in `security.xml` | one `ir.access.csv` (operations + domains) |
| `_message_post_after_hook` | `(message, msg_vals)` | `(message)` |
| Report action | `report_file` set | no `report_file` field |
| Icons | Font Awesome (`fa-sign-in`, …) | Odoo icons (`data-icon="login"`, …), also on the kiosk |
| `t-call` parameters | `t-set` children | attributes on `t-call` |
| Host notification in Discuss | *Inbox* | *Notifications* tab |
| Tests: CSRF token | `http.Request.csrf_token(self)` | `self.csrf_token()` |
| `_rec_names_search` | list | tuple |

---

## 7. Known limitations

- One host per visit (a group visiting several people: one visit per host, or note it).
- The kiosk lists all employees marked for it; very large companies may prefer a search field (not in v1).
- Time on site is wall-clock time between check-in and check-out; an automatic check-out records the time the
  scheduled action ran.
- No offline mode for the kiosk.
