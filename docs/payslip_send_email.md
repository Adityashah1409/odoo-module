# Payslip Distribution by E-mail (`payslip_send_email`)

Distribution of payslip PDFs to employees for **Odoo 19.0 / 20.0** (Community: no payroll engine needed).

The code lives in:
- `19.0/payslip_send_email/`;
- `20.0/payslip_send_email/`.

---

## 1. Planning

### 1.1 Goal

Odoo's payroll is an Enterprise app; most Community users get payslips from a social secretariat, payroll
provider or accountant as PDFs. Every month HR renames, attaches and e-mails them one by one, with the risk of
sending a payslip to the wrong person. This module turns that into: create the month, drop the PDFs, check,
send (or schedule).

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | One batch per period; import many PDFs or ZIPs at once |
| R2 | Automatic matching file → employee (badge ID or name), safe on doubt |
| R3 | E-mail to private / work / both, per company and per employee; opt-out (hand delivered) |
| R4 | Optional password on the e-mailed PDF |
| R5 | Send now or at a scheduled time; reasons when a payslip cannot be sent; resend |
| R6 | Employees see their own payslips only; HR officers see all |
| R7 | Odoo 19 and 20, no clash with Enterprise payroll models |

### 1.3 Scope (v1)

In: everything above.

Out:
- computing payslips (no payroll engine);
- splitting one big PDF into pages per employee (providers deliver one file per employee or a ZIP);
- portal access for employees without a user (they get the e-mail).

### 1.4 Acceptance criteria

- Importing `2026-10_Janssens_Lotte.pdf`, `EMP017.pdf`, `scan_0007.pdf` gives two matched payslips and one
  without employee, flagged on the batch.
- *Send now*: matched payslips are e-mailed to the private address (else work); an employee without e-mail
  shows *No e-mail address for this employee*.
- With the date-of-birth password, the attached PDF opens only with `05031990` for 5 March 1990.
- Lotte sees only her own sent payslips in *My payslips*.

### 1.5 Screenshots

`static/description/screenshots/`: batch to send, import, batch sent, batches, payslip sent, payslip not sent,
all payslips, my payslips, employee, settings.

---

## 2. Architecture

```
hr.payslip.document.batch (period, state, scheduled_date)
  ├─ Import PDFs ─► hr.payslip.import.wizard: PDFs + ZIP members
  │                  └─ hr.payslip.document._match_employee(filename, employees)
  │                        badge ∈ words  |  name words ⊆ words  |  (fallback) name words glued in filename
  │                        exactly one match, else no employee
  ├─ Send now ─► documents._send()
  │                 _check_sendable(): employee, opt-out, addresses, date of birth (password)
  │                 hr.employee._payslip_email_addresses(): employee mode → company mode
  │                 _pdf_for_mail(): pypdf encrypt with DDMMYYYY (copy; stored PDF unchanged)
  │                 mail.template.send_mail(email_to, recipient_ids=[], attachment) + chatter note
  └─ Schedule ─► ir.cron every 15 min: _cron_send_scheduled()

Security: officer (implies HR officer): all; base user: read own (user_id = user, state sent); company rules.
```

### 2.1 Design decisions

- **Own model names** (`hr.payslip.document*`) so the module can live next to Enterprise payroll.
- **Matching never guesses**: two candidates, or a second file for the same employee, leave the file unassigned.
- **E-mail only to the employee**: `send_mail` with explicit `email_to` and no recipients, so followers of the
  payslip never receive it.
- **Encrypted copy only for the e-mail**: HR keeps a readable PDF; the employee's date of birth is a common
  convention of payroll providers.
- **State per payslip** with a human reason, so a batch can be completed in several rounds.

---

## 3. Development

```
payslip_send_email/
├── models/
│   ├── hr_payslip_document.py         payslip, matching, sending, password
│   ├── hr_payslip_document_batch.py   batch, schedule, scheduled action
│   ├── hr_employee.py                 e-mail choice, addresses, smart button
│   ├── res_company.py / res_config_settings.py
├── wizard/payslip_import_wizard.py    PDFs and ZIPs
├── data/                              scheduled action, e-mail template
├── security/                          officer role, own payslips rule, company rules
├── views/                             batches, payslips, my payslips, employee, settings, menus
└── tests/test_payslip.py
```

**Try it in a shell**

```python
batch = env['hr.payslip.document.batch'].create({})          # previous month by default
env['hr.payslip.document']._match_employee('2026-10_Janssens_Lotte.pdf', env['hr.employee'].search([]))
batch.action_send_all()
```

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 payslip_send_email
tools/run_tests.sh 20.0 /path/to/odoo20 payslip_send_email
```

| Test | Covers |
| --- | --- |
| `test_names` | batch and payslip names, period label |
| `test_match_employee` | badge, word order, accents, glued words, ambiguous and partial names |
| `test_import_wizard` | PDFs + ZIP, unmatched file, second file for the same employee, empty upload |
| `test_recipients` | company modes, employee choice, opt-out |
| `test_send` | e-mail to the employee only, attachment, reasons, batch done after fixes |
| `test_password_protection` | encrypted e-mail attachment, date of birth password, stored PDF readable |
| `test_schedule` | schedule checks, not before time, sent after |
| `test_employee_access` | own sent payslips only, read-only, other payslips and batches refused, download |

Results: all 8 module tests green on 19.0 and 20.0 (the 20.0 run also counts Odoo's two web JS suites).

**Manual test**
1. Create a batch, import a few PDFs named after employees and a ZIP.
2. Assign the unmatched file, *Send now* (with a test mail server or the mail queue).
3. Log in as an employee: *Employees › My payslips*.

---

## 5. Deployment: dev → staging → production

1. **Dev:** run the tests; agree on the file naming with the payroll provider (badge ID is the safest).
2. **Staging:**
   - copy production, **disable outgoing mail servers** (staging must never e-mail real payslips);
   - fill badge IDs, private e-mails and dates of birth; import last month's PDFs and check the matching.
3. **Production:**
   - give the *Officer* role to HR only;
   - first month: send to a few employees by selecting them in the list, then the whole batch.
4. **Performance:** PDFs are attachments in the filestore; sending queues one e-mail per employee (mail queue).
5. **Rollback:** uninstalling removes payslip records and their PDFs: export them first if they must be kept.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Binary fields | base64 (`datas`, `b64decode(record.pdf_file)`) | `BinaryValue` (`attachment.raw.content`, `record.pdf_file.content`); writes accept base64 strings |
| Access rights | `ir.model.access.csv` + `ir.rule` | `ir.access.csv` (grants with domains, company restrictions) |
| Icons | Font Awesome | Odoo icons |
| Settings / logic | same | same |

---

## 7. Known limitations

- One PDF per employee and period; a combined PDF of all employees must be split first.
- The date-of-birth password is a convention, not strong secrecy; use it with private e-mail addresses.
- E-mail delivery problems after the mail queue (bounces) are visible in the e-mail log, not on the payslip.
