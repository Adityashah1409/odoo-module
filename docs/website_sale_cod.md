# Cash on Delivery: OTP and Collections (`website_sale_cod`)

End-to-end **Cash on Delivery** for the Odoo **19.0 / 20.0** eShop:
- a delivery code (OTP) for the customer;
- collections for the delivery person, confirmed with that code;
- a cash deposit that invoices and pays the order;
- availability rules.

The code lives in:
- `19.0/website_sale_cod/`;
- `20.0/website_sale_cod/`.

---

## 1. Planning

### 1.1 Goal

Odoo already ships a *Cash on Delivery* payment provider (module `delivery`, `custom_mode = 'cash_on_delivery'`).
It leaves the transaction *pending* and confirms the order, and that is where it stops:
- nothing proves the parcel reached the right person;
- nobody tracks the cash the driver carries;
- the order stays unpaid until someone registers the payment by hand.

This module closes that loop without replacing Odoo's provider.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | Keep Odoo's Cash on Delivery provider and its rules (delivery method must accept cash, countries, currencies, amounts) |
| R2 | Extra rules: minimum order amount (native in 20), excluded product categories including sub-categories |
| R3 | A random delivery code per order, shown on the confirmation page, the portal and in an e-mail; salespeople can send a new one |
| R4 | One collection per order: *To collect* → *Collected* → *Deposited*, or *Cancelled* with a reason |
| R5 | The driver collects only with the right code and the exact amount; 5 wrong codes lock the collection |
| R6 | Deposit by a manager: invoice if needed, payment in a cash journal, transaction done |
| R7 | Delivery person role that sees only its own or unassigned collections; printable receipt |
| R8 | Odoo 19 and 20 |

### 1.3 Scope (v1)

In: everything above.

Out:
- partial collections (the amount must match; otherwise cancel and re-sell);
- a dedicated mobile app or route planning (drivers use the Odoo web app / PWA);
- change given back by the driver;
- links with `stock.picking` (the collection is per order, not per parcel).

### 1.4 Acceptance criteria

- A cart with a gift card does not offer Cash on Delivery; the availability report says why.
- Paying with Cash on Delivery confirms the order and shows a 6-digit code on the confirmation page and in
  *My account › Orders*.
- The driver enters a wrong code: error with attempts left, chatter message; the right code: *Collected*.
- *Cash deposited* creates a posted invoice and one payment in the cash journal; the order is paid.
- A cancelled collection cancels the pending transaction; *Reset to collect* reopens it.
- A delivery person cannot see collections assigned to another driver.

### 1.5 Screenshots

`static/description/screenshots/` in each version:
- checkout, confirmation, portal, sales order;
- collection to collect, wrong code, collected, deposited, cancelled;
- delivery person's list, provider settings, receipt.

---

## 2. Architecture

```
Checkout ──► payment.provider._get_compatible_providers (19) / _find_available_providers (20)
             └─ _cod_filter: minimum amount (19), excluded categories (parent_of) → availability report

Pay (COD) ──► payment.transaction pending ──► _post_process (sale confirms the order)
             └─ for COD orders now in state 'sale' without a collection: sale.order._cod_start(tx)
                   ├─ cod_otp = secrets digits (length 4..10)
                   ├─ sale.cod.collection (To collect, amount_due = tx amount)
                   └─ mail template "delivery code" posted on the order

Driver ──► Collect wizard ──► _cod_check_code (consteq, attempts ≤ 5) ──► _cod_collect (exact amount) ──► Collected
Manager ─► Cash deposited ──► _cod_deposit
             ├─ order._create_invoices(final=True) + post (if "Invoice when deposited")
             ├─ account.payment.register in the provider's cash journal
             └─ tx._set_done(), is_post_processed = True, payment_id   ──► Deposited
Cancel ──► reason wizard ──► tx._set_canceled() ──► Cancelled  (Reset ──► To collect)
```

### 2.1 Design decisions

- **Reuse Odoo's provider.** No new payment provider: the module adds a tab to the existing *Cash on Delivery*
  provider and hooks the availability method. Odoo's checks (delivery method `allow_cash_on_delivery`, countries,
  currencies, amounts) keep working.
- **The collection is its own model** (`sale.cod.collection`, with chatter and activities) instead of fields on
  the order: drivers get access to collections only, never to the full sales order.
- **The code lives on the order** (`cod_otp`, restricted to salespeople) so templates and the portal can show it;
  drivers check it through the collection with `sudo()` and `consteq`.
- **Wrong attempts are kept** even though the wizard raises nothing: a wrong code reopens the wizard with an error
  message, so the counter and the chatter message are committed.
- **The deposit does the accounting** (invoice, payment) rather than the driver's *Collect*: cash is the
  company's only once it is handed in.
- **Transaction writes** use `payment_safe_write` (required by Odoo 20, harmless in 19), and the transaction is
  marked post-processed to avoid a second payment from `account_payment`.

---

## 3. Development

```
website_sale_cod/
├── models/
│   ├── payment_provider.py     COD settings, availability filter
│   ├── payment_transaction.py  start the collection after confirmation
│   ├── sale_order.py           code, state, smart button, new code
│   └── sale_cod_collection.py  collection: check code, collect, deposit, cancel, reset
├── wizard/cod_wizard.py        Collect / Cancel wizards
├── security/                   Delivery person group, record rules, access
├── data/                       sequence COD/%(year)s/, e-mail template
├── report/                     collection receipt
├── views/                      provider tab, collections, order, website templates, menus
├── static/tests/tours/         driver tour
└── tests/test_cod.py           8 functional + 2 HTTP tests
```

**Try it in a shell**

```python
order = env['sale.order'].search([('is_cod', '=', True)], limit=1)
order.cod_otp                                     # '482913'
col = order.cod_collection_ids
col._cod_collect('482913', col.amount_due)        # To collect → Collected
col.action_deposit()                              # invoice + payment, Deposited
```

**Extend**
- Another rule: return a reason from `payment.provider._cod_unavailable_reason(order)`.
- Partial collections: relax the amount check in `_cod_collect` and register the difference in `_cod_deposit`.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 website_sale_cod
tools/run_tests.sh 20.0 /path/to/odoo20 website_sale_cod
```

| Test | Covers |
| --- | --- |
| `test_availability_rules` | minimum amount, excluded category and sub-category, Odoo's delivery method rule |
| `test_order_confirmed_with_code_and_collection` | code, collection and e-mail at confirmation |
| `test_collect_with_code` | right code, exact amount, wrong amount refused |
| `test_attempt_limit_and_new_code` | 5 wrong codes lock; a new code unlocks |
| `test_deposit_invoices_and_pays` | invoice, one payment in the cash journal, transaction done, order paid |
| `test_cancel_and_reset` | reason, transaction cancelled, reset |
| `test_without_code` | provider with the code turned off |
| `test_driver_rights` | record rules for drivers, receipt rendering |
| `test_portal_shows_code` | code box in the portal order |
| `test_tour_driver_collects` | browser tour: wrong code, then right code |

Results: all 10 module tests green on 19.0 and 20.0 (the 20.0 run also counts Odoo's two web JS suites).

**Manual test**
1. Publish *Cash on Delivery*, set a cash journal, tick *Cash on Delivery* on a shipping method.
2. Buy as a portal user with Cash on Delivery: note the code on the confirmation page.
3. As a delivery person, open *COD Deliveries*, collect with a wrong then the right code.
4. As a manager, *Cash deposited*: check the invoice and the payment.

---

## 5. Deployment: dev → staging → production

1. **Dev:** run the tests; decide the code length, excluded categories and minimum amount.
2. **Staging:**
   - install on a copy of production; existing COD orders get no collection (only new confirmations do);
   - set the **cash journal** on the provider (without one, *Cash deposited* stops with a message);
   - tick *Cash on Delivery* on the shipping methods; give drivers the *Delivery person* role;
   - run one order end to end and check the e-mail template wording and the receipt.
3. **Production:**
   - install, configure as on staging, publish the provider;
   - make sure outgoing mail works: the code is sent by e-mail too;
   - train drivers: the code is asked at the door, never given by phone.
4. **Performance:** one record and one e-mail per COD order; `state` and `order_id` are indexed.
5. **Rollback:** uninstalling removes collections and codes; orders, invoices and payments stay.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Availability hook | `_get_compatible_providers` | `_find_available_providers` |
| Minimum amount | module field `cod_min_amount` on the COD tab | Odoo's own `minimum_amount` (Configuration tab); the module field is not added |
| Provider state | `state` (*Disabled / Enabled / Test*) | no `state`: `is_published`, `is_live`, `active` |
| Transaction writes | free | need `with_context(payment_safe_write=True)` |
| Access rights and record rules | `ir.model.access.csv` + `ir.rule` records in `security.xml` | one `ir.access.csv` (operations + domains; a line without a group is a restriction) |
| Report action | `report_file` set | no `report_file` field |
| Icons | Font Awesome (`fa-money`) | Odoo icons (`data-icon="payments"`) |
| Sub-template call | `t-call` with `t-set` | `t-call` with attributes |
| Tests | `CashOnDeliveryCommon` | same, plus `_create_cod_transaction`, `_run_post_processing`, `_test_user_groups = None` |

---

## 7. Known limitations

- The amount collected must equal the amount due; partial payments need a cancellation and a new order.
- Only orders confirmed after installation get a collection.
- One collection per order, not per delivery: split deliveries share one code and one collection.
- The code is shown to salespeople on purpose (customers call support); restrict the *Sales* role if needed.
- No offline mode for drivers: the Odoo web app needs a connection at the door.
