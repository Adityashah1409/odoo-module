# E-mail Cc, Bcc and Reply-To (`email_enhancement`)

Cc, Bcc and Reply-To for e-mails sent from Odoo documents, with company defaults and rules, in
**Odoo 19.0 / 20.0**.

The code lives in:
- `19.0/email_enhancement/`;
- `20.0/email_enhancement/`.

---

## 1. Planning

### 1.1 Goal

E-mails sent from Odoo documents (quotations, invoices, tasks, contacts…) go to the followers and the chosen
contacts. Companies regularly need more:
- a **Cc** to a colleague, a manager or a customer's assistant who is not (and should not become) a contact;
- a hidden **Bcc** to an archive mailbox or to accounting;
- a **Reply-To** so that answers land in a shared mailbox (sales@, support@);
- the same copies every time for the same kind of document or sender, without retyping them.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | Cc, Bcc and Reply-To in the full e-mail composer, editable before sending |
| R2 | Company defaults for the three fields |
| R3 | Rules: documents, senders, sender groups, company → Cc, Bcc, Reply-To; several rules combine |
| R4 | Bcc really delivered and never visible to the other recipients |
| R5 | Cc sent once per message, not once per recipient |
| R6 | A trace of the copies on the document, for employees only |
| R7 | Log notes never e-mailed to copies |
| R8 | Mass mode (composer on several records) supported |
| R9 | Invalid addresses refused |
| R10 | Odoo 19 and 20 |

### 1.3 Scope (v1)

In: everything above.

Out:
- copies to contacts (Odoo 20 has a native contact Cc; in 19 add them as recipients);
- Cc / Bcc on e-mails sent automatically without the composer (templates sent by code, automated actions): use
  the template's own *Cc* field;
- rule conditions on document values (amount, stage…).

### 1.4 Acceptance criteria

- Company Bcc *archive@*; rule *Quotations: copy the sales manager* (Sales Order → Cc Marc, Reply-To sales@);
  rule *Sales managers: hidden copy to accounting* (Sales Order, group Sales / Administrator → Bcc
  accounting@). Ines (sales administrator) opens the composer on a quotation: Cc Marc, Bcc archive@ +
  accounting@ and Reply-To sales@ are proposed.
- After sending: one e-mail carries `Cc: Marc`; archive@ and accounting@ are in the SMTP envelope and in no
  header; the quotation shows a note with the Cc, Bcc and Reply-To.
- A log note proposes no copy and sends nothing.
- `nope` as Cc on a rule, in the settings or in the composer is refused.

### 1.5 Screenshots

`static/description/screenshots/`: composer, chatter note, rules, rule, company defaults, outgoing e-mail.

---

## 2. Architecture

```
Composer opened (comment or mass mode)
  extra_email_cc / extra_email_bcc  ◄── mail.cc.rule._get_defaults(model, user, company)
  reply_to (comment, when empty)    ◄──   company defaults + matching rules (sudo)
        │ the user edits, clicks Send
        ▼
mail.compose.message._prepare_mail_values
  check the addresses
  comment mode ─► message values: extra_email_cc, extra_email_bcc   (+ Odoo's reply_to)
  mass mode    ─► mail values:    email_cc (merged), email_bcc
        │
        ▼ comment mode: message_post → mail.message (extra_email_*)
mail.thread._notify_by_email_get_base_mail_values  → keeps Cc / Bcc aside
mail.thread._notify_by_email_get_final_mail_values → puts them on the FIRST mail.mail only
        │
        ▼
mail.mail (email_cc, email_bcc)._send
  context {Message-Id: bcc}
  core builds the headers: To, Cc (email_cc) — no Bcc header
ir.mail_server._prepare_smtp_to_list
  + Bcc addresses of that Message-Id, once           ─► SMTP envelope
        │
composer._action_send_mail_comment → internal note "Cc / Bcc / Reply-To" on the document
```

### 2.1 Design decisions

- **E-mail addresses, not contacts**: copies are often people who must not become contacts (assistants,
  mailboxes). Odoo 20's native contact Cc stays available next to them.
- **Rules combine**: Cc and Bcc of all matching rules are added (de-duplicated; an address already in Cc is
  dropped from Bcc). Reply-To is a single value, so the first rule by sequence wins, then the company default.
- **Defaults are computed fields**, one compute per field so that giving one value never blocks the other
  default, and they stay editable: rules propose, the sender decides.
- **Bcc in the SMTP envelope only**: a `Bcc:` header would be shown to every recipient. Adding the addresses in
  `_prepare_smtp_to_list` delivers the same e-mail without revealing them. The Bcc map is keyed by
  `Message-Id` and consumed once, so a message split into several e-mails still reaches each Bcc once.
- **Cc on the first e-mail only**: Odoo may send one e-mail per recipient group; the copies get it once.
- **Message fields restricted to employees** (`groups='base.group_user'`): portal users and customers never see
  the hidden copies; the chatter note is an internal note.
- **Reply-To through Odoo's own field**: setting it switches the composer to "new thread" replies, which is what
  a Reply-To means (answers go to the given mailbox).

---

## 3. Development

```
email_enhancement/
├── models/
│   ├── mail_cc_rule.py          rules, address helpers, _get_defaults
│   ├── res_company.py           company defaults (+ validation)
│   ├── res_config_settings.py   settings fields
│   ├── mail_message.py          extra_email_cc / extra_email_bcc
│   ├── mail_thread.py           Cc / Bcc onto the notification e-mail
│   ├── mail_mail.py             email_bcc, Bcc map for the SMTP layer
│   └── ir_mail_server.py        Bcc added to the SMTP envelope
├── wizard/mail_compose_message  fields, defaults, values, chatter note, form
├── security/                    read for employees, manage for administrators, companies
├── views/                       rules, settings, outgoing e-mail
└── tests/test_email_cc.py
```

**Extend**
- Another condition (e.g. a domain on the document): extend `mail.cc.rule._applies()`.
- Defaults from the document itself (e.g. the customer's accountant): override
  `mail.compose.message._extra_email_defaults()`.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 email_enhancement
tools/run_tests.sh 20.0 /path/to/odoo20 email_enhancement
```

| Test | Covers |
| --- | --- |
| `test_defaults_from_company_and_rules` | company Bcc, document / sender / group / other-model rules, duplicates, Bcc already in Cc, Reply-To order, composer defaults |
| `test_send_comment_with_cc_bcc` | message fields, Cc on one e-mail, Bcc stored, chatter note; SMTP (mocked): Bcc in the envelope once, in no header or body, Cc header |
| `test_log_note_has_no_cc` | no copies proposed on log notes |
| `test_mass_mail` | Cc merged and Bcc on every e-mail |
| `test_validation` | invalid rule, empty rule, invalid company default, invalid composer address |

Results: all 5 module tests green on 19.0 and 20.0 (the 20.0 run also counts Odoo's two web JS suites).

**Manual test**
1. Settings: Bcc to a second mailbox of yours; create a rule for Contacts with a Cc.
2. On a contact, *Send message* › full composer: the copies are proposed; send.
3. Check the received e-mail: Cc visible, Bcc received but not shown; the note in the chatter.

---

## 5. Deployment: dev → staging → production

1. **Dev:** run the tests; list the copies wanted per department (documents, senders, mailboxes).
2. **Staging:** copy production **with outgoing mail disabled** (or a catch-all SMTP such as MailHog), set the
   defaults and rules, send from a few documents, check the queued e-mails (*Settings › Technical › Emails*:
   Cc and Bcc) and the received copies.
3. **Production:** install, set the company defaults, create the rules (start with the archive Bcc, then add
   rules per team). The outgoing mail server must accept envelope recipients that are not in the headers (all
   standard SMTP servers do).
4. **Performance:** one rule search when the composer opens; nothing at send time apart from the extra
   envelope recipients.
5. **Rollback:** uninstalling removes the rules, defaults and fields; e-mails already sent are unchanged.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Access rights and record rules | `ir.model.access.csv` + `ir.rule` | `ir.access.csv` |
| `_notify_by_email_get_final_mail_values` | `(recipient_ids, mail_values, additional_values)` | adds `recipient_cc_ids` |
| Composer | no contact Cc | native contact *Cc* next to our *Cc e-mails* |
| Settings button icon | `oi-arrow-right` | `east` |
| Rest of the code, views, tests | identical | identical |

---

## 7. Known limitations

- Only e-mails written with the composer get the rule defaults; e-mails sent by code use their template's Cc.
- Reply-To applies to the whole message; replies to that address do not come back to the chatter unless that
  mailbox is an Odoo alias.
- Copies are not followers: they do not receive later messages unless added again.
- Some SMTP providers limit the number of envelope recipients per e-mail.
