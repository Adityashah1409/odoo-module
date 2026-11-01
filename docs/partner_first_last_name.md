# Contact First, Middle and Last Name (`partner_first_last_name`)

Separate **first, middle and last name** for people in **Odoo 19.0 / 20.0**:
- Contacts, Users, CRM leads and the sign-up form;
- a configurable name order;
- automatic splitting of full names.

The code lives in:
- `19.0/partner_first_last_name/`;
- `20.0/partner_first_last_name/`.

---

## 1. Planning

### 1.1 Goal

Odoo stores a person's name as one text. Mailings ("Dear John"), sorting by last name, exports to payroll or
accounting tools and formal letters ("Smith, John") need the parts. The module adds them without changing how
the rest of Odoo uses `name`.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | First, middle (optional) and last name on people; companies unchanged |
| R2 | `name` stays the reference field and is always in sync with the parts, both ways |
| R3 | Order configurable: *First Last*, *Last First*, *Last, First*; existing names can be rewritten |
| R4 | Full names from imports, quick create, other apps split automatically, particles kept with the last name |
| R5 | Same on users; users may change their own name parts |
| R6 | CRM leads: contact first / last name, given to the contact created from the lead |
| R7 | Sign-up form asks first and last name |
| R8 | Existing data split at installation; Odoo 19 and 20 |

### 1.3 Scope (v1)

In: everything above.

Out:
- titles and suffixes ("Jr.", "III") as separate fields (Odoo's *Title* field already exists);
- per-country orders;
- portal *My account* form (it keeps the single name field and the parts follow through the split).

### 1.4 Acceptance criteria

- Typing *Anna* / *Peeters* gives the name *Anna Peeters*; changing the name to *Marie Claire Dubois* gives
  *Marie Claire* / *Dubois*.
- *Ludwig van Beethoven* gives *Ludwig* / *van Beethoven*.
- Switching to *Last, First* and applying turns *Claire Sophie Rousseau* into *Rousseau, Claire Sophie*.
- Writing a last name on several contacts at once keeps each one's first name.
- A sign-up with *Lotte* / *Janssens* creates the user *Lotte Janssens* with both parts.

### 1.5 Screenshots

`static/description/screenshots/` in each version: contact, new contact, contacts by last name, settings, contacts
after *Last, First*, user, CRM lead, sign-up.

---

## 2. Architecture

```
            name_tools.split_name(name, order, middle)   name_tools.join_name(first, middle, last, order)
                         ▲                                              ▲
res.partner.create/write ─ _partner_names_prepare(vals):
    parts in vals → name = join(parts + other parts of the record)
    only name     → parts = split(name)       (people only)
onchanges: parts → name, name → parts (guarded: no loop when they already match)

res.users.create → name from parts when missing (delegation writes the parts on the partner)
crm.lead         → contact_name ⇄ contact_first_name / contact_last_name; _prepare_customer_values()
auth_signup      → first_name / last_name accepted, name built, parts stored on the new user
settings         → order / middle names (ir.config_parameter), Apply to all contacts
```

### 2.1 Design decisions

- **`name` is not turned into a computed field.** Core code, imports and other modules write `name` directly;
  keeping it a normal field and syncing in `create` / `write` is the least invasive option.
- **Name logic in a pure-Python module** (`name_tools.py`), tested without the ORM.
- **Multi-record writes** of a single part are done record by record, because each name depends on that record's
  other parts.
- **Changing the order** never rewrites names silently: *Apply to all contacts* does it on request. The order the
  existing names were written in is remembered (`applied_order`), so names that were never split are read in
  that order, even though the settings form saves the new order before running the button.
- **Odoo 20** has no person / company switch: see section 6.

---

## 3. Development

```
partner_first_last_name/
├── __init__.py                post_init hook (split existing names)
├── models/
│   ├── name_tools.py          split / join, particles, orders
│   ├── res_partner.py         fields, sync, onchanges, mass actions
│   ├── res_users.py           creation, self-edit
│   ├── crm_lead.py            lead fields and conversion
│   └── res_config_settings.py order, middle names, preview, apply
├── controllers/main.py        sign-up
├── views/                     contact, user, lead, settings, sign-up template
├── data/                      default order
├── static/tests/tours/        sign-up tour
└── tests/test_names.py        name tools + 8 functional tests
```

**Try it in a shell**

```python
from odoo.addons.partner_first_last_name.models.name_tools import split_name, join_name
split_name('Maria de la Cruz')                     # ('Maria', '', 'de la Cruz')
p = env['res.partner'].create({'first_name': 'Anna', 'last_name': 'Peeters'})
p.name                                             # 'Anna Peeters'
```

**Extend**
- More particles: add them to `PARTICLES` in `name_tools.py`.
- Another order: add it to `ORDERS` and to `join_name()` / `split_name()`.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 partner_first_last_name
tools/run_tests.sh 20.0 /path/to/odoo20 partner_first_last_name
```

| Test | Covers |
| --- | --- |
| `test_split_and_join` | particles, commas, middle names, one word, spaces, the three orders |
| `test_create_and_write` | both directions, companies, several records, (20) contacts of VAT companies, Contacts app default |
| `test_orders_and_middle_names` | *Last, First* with middle names, *Last First* |
| `test_apply_order_and_fill_missing` | *Apply to all contacts* with the old order remembered, *Split names* |
| `test_form_onchanges` | form onchanges both ways |
| `test_users` | creation from the parts, a user changing their own last name |
| `test_crm_lead` | lead fields, conversion to a contact, onchange |
| `test_signup` | template fields and a browser sign-up |
| `test_post_init_hook` | existing names split at installation |

**Manual test**
1. Create a person with first / last name; rename it with a full name; check the parts.
2. Import a CSV with only *Name*: the parts are filled.
3. Change the order to *Last, First*, *Apply to all contacts*, check the contact list.

---

## 5. Deployment: dev → staging → production

1. **Dev:** run the tests; decide the order and whether middle names are used.
2. **Staging:**
   - install on a copy of production: the hook splits existing names (people only; see section 6 for Odoo 20);
   - check *Missing first or last name* and a sample of foreign names; fix odd cases by hand or with *Split names*.
3. **Production:**
   - install outside working hours on large databases (one write per person during the hook);
   - set the order; use *Apply to all contacts* only if names must change format.
4. **Performance:** two indexed columns; one extra dictionary operation per partner write.
5. **Rollback:** uninstalling drops the parts; names stay as they are.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Person or company | *Person / Company* switch (`is_company`) | no switch: a company is its own commercial entity with a VAT (`is_company` computed); the module shows the parts for partners without VAT and for contacts of a company |
| Splitting a lone name | always for persons | only for contacts of a company, users and contacts that already have parts (a lone name may be a company without VAT) |
| Contacts app | new records default to *Company*; pick *Person* | new records default to `is_company`; the parts still build the name |
| CRM contact fields | in the lead form and the opportunity *Contacts* tab | next to *Contact Name* in *Extra Info* (debug mode, like the core field) |
| Lead → contact | `_prepare_customer_values(name, is_company, parent_id)` | `_prepare_customer_values(name, parent_id)` |
| User self-edit | `SELF_WRITEABLE_FIELDS` | related fields with `user_writeable=True` |
| Settings | `get_param()` | typed `get_str()` / `get_bool()` |

---

## 7. Known limitations

- Splitting is a heuristic: compound first names without a middle-name setting stay together (*Jean Paul*), and
  last names of several words without a particle (*García Márquez*) are read as first + last. Fix them in the form
  or with the comma form *García Márquez, Gabriel*.
- One-word names go to the first name.
- The portal *My account* page keeps one name field.
- Odoo 20: a company without VAT created with only a name is not split (by design); a person created with only a
  name and no company is not split either: use the first / last name fields.
