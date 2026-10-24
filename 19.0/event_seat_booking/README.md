# Event Seat Booking

**Odoo 19.0** · LGPL-3 · Category: Marketing/Events

**Reserved seating for Odoo Events.** Draw the room once, sell every ticket type as a section of the seat map,
and let attendees pick their own seats on the website: premium rows, best-seat finder, a hold timer while they
pay, the seat number on the ticket, a waitlist when the show is sold out, and seat changes from *My Account*.

![Seat map on the website](static/description/screenshots/website_seat_map.png)

## Features

- **Seating plans (venue templates)**: rows × seats per row, letters or numbers for rows, aisles after given
  rows and seats, seats that are not for sale (`A1, A16`, a whole row `M`, or seat numbers), a stage label and
  **premium rows** with a surcharge (`A-C +15`). A live **preview** shows the map while you type.
- **One section per ticket type**: apply a plan to a ticket (Stalls, Balcony...) or design the layout on the ticket
  itself, then *Prepare seat arrangement*. The ticket capacity follows the number of seats for sale.
- **Seat map on the website**: *Choose your seats* replaces the ticket quantities on seat-booking events. Visitors
  click free seats or use **Find the best seats** (front rows first, side by side, close to the centre). Prices
  include premium surcharges.
- **Holds**: chosen seats are kept for N minutes (15 by default) for that visitor, with a countdown on the
  attendee page. Two visitors can never hold or book the same seat (row locks).
- **Checkout**: one attendee per seat, then the normal *website_event_sale* cart and payment. Each premium seat
  adds a *Premium seat* line to the order. Free events are confirmed at once.
- **Seat follows the registration**: paid → *Booked*; cancelled order or registration → seat released (and its
  surcharge line removed from an unpaid cart). Unpaid carts lose their seats when the hold expires; if the
  payment arrives later, the seat is given back when still free, otherwise the organizer gets an activity to
  pick another one.
- **Waitlist**: when every seat is taken, the seat page shows a *Join the waitlist* form. Released seats e-mail
  the people waiting, first come first served.
- **Portal seat change**: attendees see their seats in *My Account › Event Seats* and pick another seat in the
  same section. Cheaper or same price → changed at once; more expensive → an order for the difference, and the
  seat changes when it is confirmed.
- **Back office**: seat list and pivot, *Switch seat* wizard on registrations (shows the price difference),
  block / unblock seats, *Seats* and *Waitlist* buttons on events, seat number on registrations, the full-page
  ticket and the badge.
- **Seating dashboard**: revenue, seats sold, average seat yield, occupancy, seat status, events table,
  revenue of the last 5 days, sales per section and the latest reservations.
- Scheduled action *Events: release expired seat holds* (every 5 minutes). Multi-company rules on seats and plans.

## Screenshots

| | |
| --- | --- |
| **Event page: Choose your seats**<br>![Event](static/description/screenshots/website_event.png) | **Seat map with best seats chosen**<br>![Map](static/description/screenshots/website_seat_map.png) |
| **Attendees, with the hold countdown**<br>![Attendees](static/description/screenshots/website_attendees.png) | **Sold out: waitlist form**<br>![Waitlist form](static/description/screenshots/website_waitlist.png) |
| **My Account card**<br>![Portal home](static/description/screenshots/portal_home.png) | **My seats**<br>![Portal seats](static/description/screenshots/portal_seats.png) |
| **Change seat (current seat outlined)**<br>![Change seat](static/description/screenshots/portal_change_seat.png) | **Seating dashboard**<br>![Dashboard](static/description/screenshots/dashboard.png) |
| **Seating plans**<br>![Plans](static/description/screenshots/seat_plans.png) | **Plan with live preview**<br>![Plan](static/description/screenshots/seat_plan_form.png) |
| **Event with Seats and Waitlist buttons**<br>![Event form](static/description/screenshots/event_form.png) | **Sections (tickets) with seat counts**<br>![Tickets](static/description/screenshots/event_tickets.png) |
| **Section layout and seat map**<br>![Section](static/description/screenshots/section_seating.png) | **Seats of an event**<br>![Seats](static/description/screenshots/seats_list.png) |
| **Seat analysis**<br>![Pivot](static/description/screenshots/seats_pivot.png) | **Registration with its seat**<br>![Registration](static/description/screenshots/registration_form.png) |
| **Switch seat wizard**<br>![Switch](static/description/screenshots/switch_seat.png) | **Waitlist**<br>![Waitlist](static/description/screenshots/waitlist.png) |
| **Settings**<br>![Settings](static/description/screenshots/settings.png) | **Seat on the ticket**<br>![Ticket](static/description/screenshots/ticket_report.png) |

## Installation

Add `19.0/` of this repository to your addons path and install **Event Seat Booking**.
- **Odoo dependencies**: `website_event_sale` (Events, Website, eCommerce, Sales).
- **Python**: nothing extra.

## Configuration

1. *Events › Configuration › Settings › Seat booking*: hold time, *Best available seats*, *Seat change from the
   portal* and the surcharge product.
2. *Events › Configuration › Seating Plans*: create the rooms (rows, seats, aisles, blocked seats, premium rows).
3. On an event, tick **Seat booking**, add one ticket per section, open the section (*Seats* button in the
   tickets list), choose the plan, *Apply*, then *Prepare seat arrangement*.
4. Publish the event. The website shows *Choose your seats*.
5. Access: event users manage seats, plans and the waitlist; the registration desk can read them and switch
   seats.

## Technical overview

| Part | Role |
| --- | --- |
| `event.seat.layout.mixin` | Layout fields, rule parsing, grid cells (aisles, blocked seats, premium rows), previews |
| `event.seat.plan` / `event.seat.surcharge` | Reusable plans and premium rows |
| `event.seat` | One seat: section, row, number, position, price, state (available / held / booked / blocked), hold token and expiry, registration, surcharge order line; holds, best block, cron |
| `event.event.ticket` (inherit) | Section layout, *Prepare / Clear*, capacity sync, map data |
| `event.event` (inherit) | *Seat booking* flag, totals, sold-out check, waitlist notification, dashboard data |
| `event.registration` (inherit) | `seat_id`, seat follows the registration state, conflicts, *Switch seat* |
| `sale.order` (inherit) | Seat state after confirm / cancel; seat upgrade orders |
| `event.seat.waitlist` | Waitlist and notification e-mail |
| `controllers/main.py` | Seat page, hold and best-seat JSON routes, attendees page, premium lines in the cart, waitlist |
| `controllers/portal.py` | *My seats* and seat change |
| `static/src/js/seat_map.js` | Website seat map (plain JavaScript) |
| `static/src/dashboard/` | OWL dashboard |

## Odoo 19 notes

- Settings are stored with `ir.config_parameter.get_param` / `set_param`. *Best available seats* is switched on by
  a post-install hook, because an unchecked boolean setting removes its parameter.
- The *Event Seats* card on *My Account* is a QWeb entry (`portal.portal_docs_entry`).
- Access rights in `ir.model.access.csv`; the dashboard uses OWL 2 and Font Awesome icons.

## Tests

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 event_seat_booking
```

22 tests:
- layout: seat generation, aisles, blocked rules, numeric rows, plans, previews, rebuild limits, block / unblock,
  best seats;
- booking: holds and expiry, registration lifecycle and waitlist e-mail, unpaid holds released and given back or
  in conflict, *Switch seat*, upgrade orders, dashboard, multi-slot events refused;
- website: seat page and best seats, paid booking with a premium line, cancelled cart, free booking, taken or
  expired seats, sold out and waitlist, portal seat change (same price and upgrade order), and a browser tour.

## Full guide

[docs/event_seat_booking.md](../../docs/event_seat_booking.md) · Odoo 20.0: [`20.0/event_seat_booking`](../../20.0/event_seat_booking)

---
Author: Aditya Shah · License: LGPL-3
