# Sales Order E-mail Notifications (`sale_order_email_notification`)

Rule-based e-mail notifications for quotations and orders in **Odoo 19.0 / 20.0**.

The code lives in:
- `19.0/sale_order_email_notification/`;
- `20.0/sale_order_email_notification/`.

---

## 1. Planning

### 1.1 Goal

Odoo notifies followers of an order, but companies need targeted alerts: management for every confirmed order,
finance only above an amount, the warehouse when an order is cancelled, the shop team for eCommerce orders, a
shared mailbox that is not an Odoo user. Following orders by hand does not scale and floods people with chatter
messages.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | Several rules, each with a trigger: new quotation, confirmed, cancelled |
| R2 | Conditions: channel (back office / eCommerce), sales teams, minimum total, company |
| R3 | Recipients: users, free addresses, salesperson, team leader, customer |
| R4 | Template per rule, optional order PDF |
| R5 | Internal e-mails stay out of the order chatter and portal; a short log stays on the order |
| R6 | Managed by Sales administrators, triggered by everybody |
| R7 | Odoo 19 and 20 |

### 1.3 Scope (v1)

In: everything above.

Out:
- other triggers (quotation sent, delivered, invoiced): Odoo automation rules cover those;
- SMS / chat notifications;
- digests (one e-mail per order and rule).

### 1.4 Acceptance criteria

- Rule *Big export orders* (confirmed, team Export, ≥ 5,000, team leader + finance@): confirming a 17,776.70
  Export order e-mails Sara and finance@, attaches the PDF, logs it on the order; a 1,000 order or a Benelux
  order sends nothing.
- Cancelling an order with a *Cancelled* rule e-mails planning@.
- The internal e-mail is not visible in the order's chatter.

### 1.5 Screenshots

`static/description/screenshots/`: rules, rule, e-mails received (big order, new quotation), order log,
cancelled order.

---

## 2. Architecture

```
sale.order.create  ──(draft, back office)──► _notify_order_rules('create')
sale.order.action_confirm ──(now 'sale')──► _notify_order_rules('confirm')
sale.order._action_cancel ──(now 'cancel')─► _notify_order_rules('cancel')
                                              │ (context skip_order_notification to silence)
                                              ▼
sale.order.notification.rule (sudo, trigger)
   _matches(order): company, channel (website_id if eCommerce), teams, min total (converted)
   _internal_recipients(order): users + salesperson + team leader (partners) | addresses (minus duplicates)
   _send(order):
      template.send_mail(email_values={recipient_ids, email_to, model: False, res_id: False, attachments})
      customer: customer template / Odoo confirmation template, linked to the order
      order.message_post(note "Notification … sent to …"), rule counters
```

### 2.1 Design decisions

- **Rules instead of one setting**: different people need different orders.
- **Unlinked internal e-mails** (`model: False`): the e-mail is rendered with the order but not attached to it,
  so the chatter and the customer portal stay clean; a one-line note keeps the trace.
- **No dependency on eCommerce**: the channel uses `website_id` when the field exists.
- **New eCommerce carts ignored** for *New quotation* rules: carts are created at the first *Add to cart*.
- **sudo inside the hooks**: salespeople cannot read every rule's recipients' details, but their actions must
  trigger the rules.

---

## 3. Development

```
sale_order_email_notification/
├── models/
│   ├── sale_order_notification_rule.py   rules, matching, recipients, sending, test
│   └── sale_order.py                     triggers
├── data/                                 e-mail template, two archived example rules
├── security/                             read for salespeople, manage for administrators, companies
├── views/                                rules list / form / search, menu
└── tests/test_order_notification.py
```

**Extend**
- Another trigger: add a selection value and call `_notify_order_rules('<value>')` from the right method.
- Another condition: extend `_matches()`.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 sale_order_email_notification
tools/run_tests.sh 20.0 /path/to/odoo20 sale_order_email_notification
```

| Test | Covers |
| --- | --- |
| `test_confirm_rule_recipients` | users, addresses, salesperson, leader, no duplicate, counter, log, e-mail out of the chatter |
| `test_create_and_cancel_triggers` | new quotation, cancellation, silent context |
| `test_filters` | team, minimum total, channel without eCommerce |
| `test_customer_and_pdf` | customer copy, PDF attachment |
| `test_inactive_rule_and_test_button` | archived rule, *Send a test* |
| `test_email_list_validation` | invalid address refused |
| `test_access` | salespeople read only, still trigger rules |

Results: all 7 module tests green on 19.0 and 20.0 (the 20.0 run also counts Odoo's two web JS suites).

**Manual test**
1. Create a rule for confirmed orders to yourself; confirm an order; check *Settings › Technical › Emails*.
2. *Send a test* on a rule.

---

## 5. Deployment: dev → staging → production

1. **Dev:** run the tests; write down the rules with the sales manager.
2. **Staging:** copy production **with outgoing mail disabled**, create the rules, confirm a few orders, read the
   queued e-mails.
3. **Production:** install, create or activate the rules, *Send a test* on each.
4. **Performance:** one search on rules per order event; e-mails go through the mail queue; the PDF is rendered
   only for rules that attach it.
5. **Rollback:** uninstalling removes the rules; e-mails already sent stay in the mail log.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Access rights and record rules | `ir.model.access.csv` + `ir.rule` | `ir.access.csv` |
| Code, template, views | identical | identical |

---

## 7. Known limitations

- One e-mail per order and rule; overlapping rules can notify the same person twice (one per rule).
- The minimum total compares the order total converted to the company currency at the order date.
- eCommerce *New quotation* notifications are not supported on purpose (use *Order confirmed* with the eCommerce
  channel).
