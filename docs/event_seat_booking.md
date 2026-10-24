# Event Seat Booking (`event_seat_booking`)

Reserved seating for **Odoo 19.0 / 20.0 Events**. Organizers draw a room once (rows, aisles, seats not for sale,
premium rows), use it for any ticket type, and attendees choose their own seats on the website. Seats are held
while the visitor pays, follow the registration (paid, cancelled, late payment), appear on the ticket, open a
waitlist when everything is sold, and can be changed later from *My Account*.

The code lives in:
- `19.0/event_seat_booking/`;
- `20.0/event_seat_booking/`.

---

## 1. Planning

### 1.1 Goal

Odoo Events sells tickets by quantity. Theatres, concert halls, cinemas, conferences with assigned tables and
gala dinners need **specific seats**: the customer wants to see the room and pick a place, the organizer wants to
price front rows higher and never sell the same seat twice.

The module adds that on top of the standard flow (`website_event_sale`): same tickets, same cart, same payment
providers, same registrations and badges. Only the choice of the seat is new.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | Describe a room: rows × seats, row names (A, B... or 1, 2...), aisles after rows and seats, seats not for sale, stage label |
| R2 | Reusable seating plans, applied to any event ticket; one ticket type = one section of the map |
| R3 | Premium rows with a surcharge, shown on the map and charged in the order |
| R4 | Website seat map: pick seats, see prices, *Find the best seats* for N people |
| R5 | Seats held for a visitor during checkout, with a visible countdown; no double booking, even with concurrent visitors |
| R6 | Seat state follows the registration and the order: paid, cancelled, unpaid and expired, paid late |
| R7 | Seat number on registrations, tickets and badges |
| R8 | Waitlist when sold out, notified when seats are released |
| R9 | Attendees change their seat from the portal; upgrades are paid |
| R10 | Back office: seat list, block / unblock, switch seat, dashboard |
| R11 | Same features and tests on Odoo 19 and 20 |

### 1.3 Scope (v1)

**In scope:** everything above.

**Out of scope:**
- free-form room drawings (curved rows, tables of different shapes): the map is a grid with aisles;
- events with time slots (*Multiple Slots*): a seat map is per event, not per slot;
- reselling a seat between attendees;
- seat selection in the back-office sale order configurator (organizers assign seats on the registration).

### 1.4 Roles

| Role | Can |
| --- | --- |
| Event manager | Everything, including seating plans |
| Event user | Sections, seats (prepare, block, release), waitlist, switch seat, dashboard |
| Registration desk | Read seats and plans, switch seats |
| Website visitor | Choose seats, book, join the waitlist |
| Portal user | See their seats, change seat (when enabled) |

### 1.5 Acceptance criteria

- A plan of 10 × 16 with aisles after seats 4 and 12, after row 5, and `A1, A16` not for sale gives 158 seats on
  sale, drawn with the gaps; applying it to a ticket and preparing creates those seats, and the ticket capacity
  becomes 158.
- On the website, two visitors cannot hold the same seat; the second one gets "just taken".
- A visitor who picks a premium seat pays ticket price + surcharge: the cart has the ticket line and one
  *Premium seat* line per premium seat.
- Paying the order books the seats; cancelling it releases them. An unpaid cart releases its seats after the
  hold time; paying later gives the seat back if it is still free, otherwise creates an activity for the
  organizer.
- When every seat is taken, the event page links to the waitlist and released seats e-mail the people waiting.
- A portal user moving to a cheaper or same-price seat is moved at once; moving to a premium seat creates an
  order for the difference and moves the seat when the order is confirmed.

### 1.6 Screenshots

These are from Odoo 19. The Odoo 20 ones are in `20.0/event_seat_booking/static/description/screenshots/`.

![Seat map](../19.0/event_seat_booking/static/description/screenshots/website_seat_map.png)
![Attendees](../19.0/event_seat_booking/static/description/screenshots/website_attendees.png)
![Dashboard](../19.0/event_seat_booking/static/description/screenshots/dashboard.png)
![Plan](../19.0/event_seat_booking/static/description/screenshots/seat_plan_form.png)
![Portal](../19.0/event_seat_booking/static/description/screenshots/portal_change_seat.png)

---

## 2. Architecture

```
event.seat.plan ──(Apply)──► event.event.ticket (section) ──(Prepare)──► event.seat × N
   layout mixin                 layout mixin + premium rows                 name, row, number, position,
   premium rows                 seats_max = seats for sale                  price, state, hold, registration

Website                                    Server
/event/<id>/seats ───────── map data ◄──── ticket._seat_map_data(session token)
  click / best seats ── JSON /event/seats/best ──► seats._best_block(n)
  Continue ─────────── JSON /event/seats/hold ──► seats._hold(token)  (SELECT ... FOR UPDATE NOWAIT)
/event/<id>/seats/attendees ── form ──► /event/<id>/registration/confirm   (standard route)
                                          _create_attendees_from_registration_post
                                            ├─ checks the holds of this session
                                            ├─ standard: cart lines + registrations (draft)
                                            └─ one "Premium seat" line per premium seat
sale.order.action_confirm ─► registrations open ─► seat booked
sale.order._action_cancel ─► registrations cancel ─► seat released ─► waitlist e-mails
cron (5 min) ─► expired holds released; unpaid registrations keep a pointer to their former seat
```

Seat states:

```
available ──hold(token)──► held ──registration paid/free──► booked
    ▲                        │ expires (cron) / released          │ cancelled / switched
    └────────────────────────┴────────────────────────────────────┘
blocked ◄──► available   (organizer; never for held or booked seats)
```

### 2.1 Design decisions

- **A section is a ticket type.** Prices, sale dates, limits and products already live on `event.event.ticket`,
  and the cart, the registrations and the reports already know it. Adding the layout to the ticket keeps every
  standard feature working; the event just has several sections.
- **Seats are records** (`event.seat`), not JSON. Locking a row (`FOR UPDATE NOWAIT`) is the simplest reliable
  protection against two visitors taking the same seat. Reporting (pivot, list, dashboard) comes for free.
- **One layout mixin** for plans and tickets: the same rules parse `A1, A16, M, R3, 7`, compute aisles and premium
  rows, and draw the previews. A plan is copied to the ticket (*Apply*), so editing a plan never moves sold seats.
- **Holds use the visitor's session token.** Only the session that holds a seat can register it. The token is
  passed to the registration through the context, so the standard controller is reused unchanged.
- **The seat follows the registration**, not the other way round. In Odoo the registration state is computed from
  the order (`event_sale`), so the module reacts on `sale.order.action_confirm` / `_action_cancel` and on
  registration writes. An unpaid registration keeps `seat_released_id` after expiry, so a late payment can get
  the seat back or raise an activity.
- **Premium price as a separate order line.** The ticket price stays the ticket price (reports by ticket stay
  right); each premium seat adds a line with the surcharge product. Cancelling a seat removes its line from an
  unpaid cart.
- **Ticket capacity = seats for sale.** Odoo's own sold-out logic, availability badges and limits keep working.
- **Plain JavaScript on the website** (`seat_map.js`), no OWL: it loads with the frontend bundle, works with
  server-rendered HTML and degrades to a readable page.

---

## 3. Development

```
event_seat_booking/
├── controllers/
│   ├── main.py                 seat page, JSON hold / best seats, attendees page, premium lines, waitlist
│   └── portal.py               My seats, change seat, upgrade order
├── data/                       surcharge product, waitlist e-mail, cron (+ portal entry on 20)
├── models/
│   ├── seat_layout.py          layout mixin, rule parsing, grid cells, previews, premium rows
│   ├── event_seat_plan.py      seating plans
│   ├── event_seat.py           seats, holds, best block, cron
│   ├── event_ticket.py         sections: apply plan, prepare / clear seats, map data
│   ├── event_event.py          seat booking flag, totals, sold out, waitlist, dashboard data
│   ├── event_registration.py   seat on registrations, state follow-up, conflicts
│   ├── event_seat_waitlist.py  waitlist
│   ├── sale_order.py           confirm / cancel hooks, upgrade orders
│   └── res_config_settings.py  settings
├── report/                     seat on the full-page ticket and the badge
├── static/src/js/seat_map.js   website seat map
├── static/src/dashboard/       OWL dashboard
├── views/                      back office, website and portal templates, menus
├── wizard/                     Switch seat
└── tests/                      22 tests + tour
```

**Run it locally**

```bash
python odoo-bin -d seats --addons-path=addons,odoo/addons,/path/to/odoo-module/19.0 -i event_seat_booking
```

Then: *Events › Configuration › Seating Plans* → create a plan; open an event, tick *Seat booking*, open a
ticket with the *Seats* button, choose the plan, *Apply*, *Prepare seat arrangement*; publish the event and open
`/event/<id>/seats`.

**Useful shell snippets**

```python
ticket = env['event.event.ticket'].browse(1)
ticket.seat_ids._best_block(4).mapped('name')        # what "Find the best seats" proposes
ticket._seat_map_data()['rows'][0]                    # the cells of the first row
env['event.seat']._cron_release_expired_holds()       # release holds now
```

**Extend**
- Another price rule (per seat, per column): override `event.seat.surcharge._amount_for` or set `surcharge` on
  seats after *Prepare*.
- Another "best seat" policy: override `event.seat._best_block`.
- More data on the map: extend `event.event.ticket._seat_map_data` and the `seat_map_grid` template.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 event_seat_booking
tools/run_tests.sh 20.0 /path/to/odoo20 event_seat_booking
```

| File | Covers |
| --- | --- |
| `test_layout.py` | Seat generation with aisles and blocked seats, numeric rows and every blocking rule, plan apply and previews, rebuild limits (busy seats), block / unblock and capacity, best seats (side by side first, then across an aisle, not enough seats) |
| `test_booking.py` | Holds (same visitor, other visitor, expired, blocked, no token), registration lifecycle with the waitlist e-mail, unpaid hold released then given back or in conflict, *Switch seat* with price difference, upgrade order, dashboard data, multi-slot events refused |
| `test_website.py` | Event page and seat page, hold and best-seat routes, paid booking with a premium line and confirmation, cancelled cart, free booking, taken and expired seats, sold out with waitlist link and form, portal seat change (same price and upgrade order), browser tour (best seats → attendees → confirmation) |

**Manual test**
1. Two private windows on the same event: pick the same seat in both. The second gets "just taken".
2. Pick a premium seat, continue to the cart: the *Premium seat* line is there. Pay with the demo provider: the
   seat turns *Booked*, the ticket PDF shows it.
3. Leave a cart unpaid for longer than the hold time (or run the cron): the seat is free again.
4. Book every seat of a small event: the event page shows *Sold Out* with *Join the waitlist*. Cancel one
   registration: the people waiting get an e-mail.
5. As a portal user, change to a more expensive seat: an order for the difference opens; confirm it and the
   seat changes.

---

## 5. Deployment: dev → staging → production

1. **Dev:**
   - run the tests on both versions;
   - build the rooms as seating plans and check the previews against the real venue (row names, aisles,
     wheelchair spaces as *not for sale*).
2. **Staging:**
   - restore a copy of production; install the module (it depends on `website_event_sale`);
   - set the hold time (10–20 minutes is usual; it must be longer than the payment provider's checkout);
   - set up one real event, prepare its sections and run a full purchase with the test payment provider;
   - check the ticket and badge reports and the confirmation e-mail.
3. **Production:**
   - install, configure *Settings › Seat booking*;
   - for events already on sale, tick *Seat booking* only before sales start: existing registrations have no
     seat (assign them with *Switch seat* if needed);
   - make sure the scheduled action *Events: release expired seat holds* is active.
4. **Capacity:** a seat page reads the seats of the event in one search per section. Holds lock only the chosen
   rows, so busy on-sales are limited by the number of workers, not by the room size. Run several workers
   (`--workers`) and load-test a large room on staging before a big on-sale.
5. **Monitoring:**
   - the seating dashboard (seats on hold, occupancy);
   - *Seats* filtered on *On hold* (stuck carts);
   - registrations with the *Assign a seat* activity (late payments);
   - the server log (`event_seat_booking`).
6. **Rollback:** untick *Seat booking* on an event to go back to ticket quantities (seats stay for reporting).
   Uninstalling removes seats, plans and the waitlist; registrations and orders stay.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Settings / parameters | `get_param` / `set_param`; "on" defaults set by a post-install hook | Typed `get_bool` / `get_int` / `set_bool` |
| Website in controllers | `request.website` | `request.env.website` |
| *My Account* card | QWeb `portal.portal_docs_entry` + `_prepare_home_portal_values` | `portal.entry` record + `_prepare_portal_counter_values` |
| Access rights | `ir.model.access.csv` + `security.xml` | `ir.access.csv` |
| Dashboard | OWL 2 (`useState`), Font Awesome | OWL 3 (`proxy`, `this.` in templates), Material Symbols |
| Event, sale, website_event_sale APIs used | same code | same code |

---

## 7. Known limitations

- **Grid layouts.** Rows are straight lines of seats with aisles; curved or staggered rows are drawn as a grid.
- **No time slots.** Events with *Multiple Slots* cannot use seat booking (refused with a clear message).
- **Back-office sales.** Orders created in the back office do not ask for seats; give seats on the
  registrations (*Switch seat*) or let customers book on the website.
- **Seat change scope.** From the portal, attendees change seats within their section only; moving to another
  section (another ticket) is done by the organizer.
- **Waitlist.** People on the waitlist are told that seats are free; they still book like everybody else (no
  automatic reservation for them).
- **Holds per session.** A visitor switching browser or device mid-checkout loses the hold and chooses again.
