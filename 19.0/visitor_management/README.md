# Visitor Management

**Odoo 19.0** · LGPL-3 · Category: Human Resources

Know **who is in the building**:
- register expected visitors and send them an **invitation with a pass code**;
- **check visitors in and out** at the reception or on a **self-service kiosk**;
- the **host is notified** when the visitor arrives;
- print a **visitor pass** with a QR code;
- analyse visits by department, host and type.

![Visits](static/description/screenshots/visits_kanban.png)

## Features

- **Visits** (`VIS/2026/0001`): *Expected* → *On site* → *Checked out*, or *Cancelled*.
  - Visitor: name, contact (optional), company, phone, e-mail, number of people, vehicle plate.
  - Visit: host (employee), department (from the host), visit type, category, destination, purpose, notes.
  - Times: expected date, check-in, check-out and **time on site**.
  - A unique 6-character **pass code** (no look-alike characters such as 0/O or 1/I).
- **Views**: kanban by status with *Check in* / *Check out* buttons on the cards, list, calendar of expected
  visits, pivot and graph; filters *Today*, *On site*, *My visitors*, *From the kiosk*.
- **Host notification** at check-in: a message to the host's work contact (inbox or e-mail). From the kiosk it is
  sent in the company's name.
- **Invitation** e-mail (template, editable before sending) with the date, the host, the meeting place and the
  pass code.
- **Self check-in kiosk** (`/visitor/kiosk/<secret>`, no login, made for a tablet):
  - *invited* visitors type their pass code;
  - *walk-ins* enter their name, company, phone, e-mail, choose their host and the reason;
  - the welcome screen gives the pass code, the meeting place and says the host was told;
  - *check out* with the pass code.
- **Visit types** with a usual duration: a visit that lasts longer is flagged *Longer than usual*. Types can be
  hidden from the kiosk (e.g. contractors).
- **Categories** (Regular, VIP, Escorted, …): *Must be escorted* shows an alert on the visit and is printed on the
  pass.
- **Destinations** with directions, printed on the pass and shown on the kiosk.
- **Visitor pass** (A6 PDF): company, visitor, host, destination, date, QR code of the pass code.
- **Automatic check-out** of visitors forgotten on site after N hours (scheduled action).
- **Employees**: *Visitors* smart button; *Can be chosen on the visitor kiosk* option.
- **Roles**: *Receptionist* (visits) and *Administrator* (also configuration and settings).

## Screenshots

| | |
| --- | --- |
| **Today's visits**<br>![Kanban](static/description/screenshots/visits_kanban.png) | **List**<br>![List](static/description/screenshots/visits_list.png) |
| **Expected visit**<br>![Expected](static/description/screenshots/visit_expected.png) | **Invitation with the pass code**<br>![Invitation](static/description/screenshots/invitation.png) |
| **Escorted visitor on site**<br>![Escort](static/description/screenshots/visit_escort.png) | **Longer than usual**<br>![Overstay](static/description/screenshots/visit_overstay.png) |
| **Kiosk: home**<br>![Kiosk](static/description/screenshots/kiosk_home.png) | **Kiosk: walk-in check-in**<br>![Check in](static/description/screenshots/kiosk_check_in.png) |
| **Kiosk: welcome**<br>![Welcome](static/description/screenshots/kiosk_welcome.png) | **Kiosk: invited visitor**<br>![Invited](static/description/screenshots/kiosk_welcome_invited.png) |
| **Kiosk: check-out**<br>![Check out](static/description/screenshots/kiosk_check_out.png) | **Kiosk: goodbye**<br>![Goodbye](static/description/screenshots/kiosk_goodbye.png) |
| **Host notification**<br>![Inbox](static/description/screenshots/host_inbox.png) | **Visitor pass**<br>![Pass](static/description/screenshots/pass.png) |
| **Calendar**<br>![Calendar](static/description/screenshots/visits_calendar.png) | **Analysis**<br>![Graph](static/description/screenshots/analysis_graph.png) |
| **Time on site by department**<br>![Pivot](static/description/screenshots/analysis_pivot.png) | **Employee: Visitors button**<br>![Employee](static/description/screenshots/employee.png) |
| **Visit types**<br>![Types](static/description/screenshots/visit_types.png) | **Settings**<br>![Settings](static/description/screenshots/settings.png) |

## Installation

Add `19.0/` of this repository to your addons path and install **Visitor Management**.
- **Odoo dependencies**: `hr`, `mail`.
- **Python**: `qrcode` (already required by Odoo).

## Configuration

1. *Settings › Users*: give receptionists the **Visitors: Receptionist** role.
2. *Visitors › Configuration › Settings*:
   - **Notify the host** at check-in;
   - **Automatic check-out** after N hours (0 = never);
   - **Kiosk**: copy the link to the reception tablet; *New link* makes the old one stop working; welcome text.
3. *Visitors › Configuration*: visit types (usual duration, offered on the kiosk), categories (escort),
   destinations (directions).
4. *Employees › Settings tab*: untick *Can be chosen on the visitor kiosk* for people who do not receive visitors.

## Technical overview

| Part | Role |
| --- | --- |
| `visitor.visit` | The visit: sequence, pass code, flow, host notification, invitation, auto check-out, kiosk methods |
| `visitor.visit.type` / `visitor.visit.category` / `visitor.destination` | Configuration |
| `hr.employee` | Kiosk option, *Visitors* smart button |
| `res.company` / `res.config.settings` | Kiosk secret, notification, auto check-out, welcome text |
| `controllers/kiosk.py` | Public kiosk pages (token checked, CSRF-protected forms) |
| `report/` | Visitor pass with a QR code |

## Tests

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 visitor_management
```

The tests cover:
- references and unique pass codes;
- check-in with host notification, check-out with the time on site, wrong transitions;
- notification turned off; cancel and reset;
- *Longer than usual* and the automatic check-out (with 0 = never);
- contact onchange and the invitation e-mail;
- check-out before check-in refused;
- access rights (receptionist, employee, public employee profile of the host);
- the pass report;
- the kiosk: pass code, walk-in, hidden hosts and types, check-out, wrong token, form errors, company as author.

## Full guide

[docs/visitor_management.md](../../docs/visitor_management.md) · Odoo 20.0: [`20.0/visitor_management`](../../20.0/visitor_management)

---
Author: Aditya Shah · License: LGPL-3
