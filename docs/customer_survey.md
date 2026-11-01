# Customer Surveys (`customer_survey`)

Surveys run from the customer for **Odoo 19.0 / 20.0**:
- send by e-mail, fill in with the customer, print blank forms;
- answers, scores and history on the contact;
- analysis of customer answers.

The code lives in:
- `19.0/customer_survey/`;
- `20.0/customer_survey/`.

---

## 1. Planning

### 1.1 Goal

Odoo's Surveys app is organised around the survey: you invite people and read results per survey. Sales and
service teams think the other way round: *what did this customer answer, when did we last ask, and can I fill it
in with them right now?* The module adds that customer view without changing how surveys work.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | Start a survey from a contact: by e-mail, filled in with the customer, or as a blank print |
| R2 | A survey per contact, else one default customer survey |
| R3 | Every answer knows the customer, how it was collected and by whom |
| R4 | Answers, count and last survey date on the contact; a company sees its contacts' answers |
| R5 | Send to many contacts from the list |
| R6 | Analysis: by survey, collection mode, salesperson, country, month; average score |
| R7 | Odoo 19 and 20 |

### 1.3 Scope (v1)

In: everything above.

Out:
- automatic surveys after a sale, delivery or ticket (can be added with an automation rule calling
  `action_customer_survey_send`);
- answers in the customer portal;
- NPS-specific question types (use a simple choice with scores).

### 1.4 Acceptance criteria

- On *Delta Logistics*, *Fill in now* opens the survey; the finished answer shows *Filled in with the customer*,
  *Collected by Lucas Peeters* on the company and on Nora's contact.
- *Send by e-mail* on two contacts creates two answers marked *Sent by e-mail*; unanswered ones can be reminded.
- Ticking *Default customer survey* on a survey un-ticks the previous one.
- The pivot shows the average score per survey and collection mode.

### 1.5 Screenshots

`static/description/screenshots/` in each version: contact tab, send by e-mail, fill in (start, question),
customer answers, pivot, graph, bulk send, survey options.

---

## 2. Architecture

```
res.partner (Surveys tab)
  ├─ Fill in now ──► survey._create_answer(user=employee, check_attempts=False,
  │                     customer_partner_id=contact, customer_mode='visit', customer_collected_by_id=uid)
  │                  └─► act_url /survey/start/<survey token>?answer_token=… (new tab)
  ├─ Send by e-mail ─► survey.action_send_survey() with default_partner_ids + default_customer_mode='email'
  │                    (Odoo's invite wizard creates the answers; the context default marks them)
  ├─ Print blank form ─► survey.action_print_survey()
  └─ answers = survey.user_input where customer_partner_id child_of contact

survey.user_input
  customer_partner_id  stored compute from partner_id (not for employees), or set explicitly (visit)
  customer_mode / customer_collected_by_id
  customer_country_id / customer_salesperson_id / customer_commercial_id  (stored related, for analysis)
  scoring_percentage aggregator = avg
```

### 2.1 Design decisions

- **Visit answers belong to the employee.** In Odoo 19 a logged-in user cannot open an answer of another partner
  (*Survey Access Error*), and in both versions a survey answered "as the customer" would send certification or
  score e-mails to the customer. So the participant is the employee and the customer is a separate field.
- **Odoo's invitation wizard is reused** for e-mails (templates, deadlines, resend), only pre-filled.
- **Customer is computed from the participant** for answers created elsewhere (Odoo's own invitations), except
  for internal users answering for themselves.
- **Company view**: a company shows the answers of all its contacts (`child_of`).
- **Average scores**: summing percentages in groups is meaningless, so the score aggregates as an average.

---

## 3. Development

```
customer_survey/
├── models/
│   ├── res_partner.py         survey of the contact, answers, actions
│   ├── survey_survey.py       default customer survey, Customers button
│   └── survey_user_input.py   customer fields, average score, continue action
├── views/                     contact tab and list action, customer answers, survey options
└── tests/test_customer_survey.py
```

**Try it in a shell**

```python
contact = env['res.partner'].browse(9)
contact.with_user(env.ref('base.user_admin')).action_customer_survey_start()   # visit answer + URL
contact.customer_survey_answer_ids.mapped('customer_mode')
```

**Extend**
- Send automatically after an event: an automation rule with *Execute code*
  `action = record.partner_id.action_customer_survey_send()` (opens the wizard) or call Odoo's
  `survey.invite` directly for an unattended send.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 customer_survey
tools/run_tests.sh 20.0 /path/to/odoo20 customer_survey
```

| Test | Covers |
| --- | --- |
| `test_single_default_survey` | one default survey |
| `test_send_by_email` | wizard pre-filled, answers marked e-mail, contact survey over default |
| `test_fill_in_with_customer` | employee participant, customer set, limited attempts ignored, continue |
| `test_stats_and_answers_action` | last date, company sees contacts' answers, answers action, survey button |
| `test_employee_answers_are_not_customer_answers` | employees vs native invitations |
| `test_no_survey` | clear error, blank print URL |
| `test_bulk_server_action` | *Send survey* on several contacts |
| `test_employee_opens_visit_survey` (HTTP) | the employee opens the visit survey; 19: Odoo refuses another partner's answer |

Results: all 8 module tests green on 19.0 and 20.0 (the 20.0 run also counts Odoo's two web JS suites).

**Manual test**
1. Mark a survey as default customer survey.
2. On a contact: *Fill in now*, answer, check the tab; *Send by e-mail* to yourself, answer from the e-mail.
3. *Surveys › Customer answers*: pivot by collection mode.

---

## 5. Deployment: dev → staging → production

1. **Dev:** run the tests; design the survey (scored choices give a satisfaction score).
2. **Staging:** install; existing answers of customers get their customer automatically (stored compute on
   install); check the invitation template wording and the sender.
3. **Production:** install, set the default survey, give the *Surveys: User* role to the teams that survey
   customers.
4. **Performance:** three stored related fields and one indexed field on answers; the contact tab runs one search.
5. **Rollback:** uninstalling removes the customer fields; answers stay in Surveys.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Opening an answer of another partner with its token | refused (*Survey Access Error*) | allowed (no partner check with a token) |
| Visit answers | employee as participant (needed) | same (kept for scores and e-mails) |
| Icons | Font Awesome | Odoo icons |
| Code | identical | identical |

---

## 7. Known limitations

- *Continue* works for the employee who started the visit (Odoo links the answer to that user).
- One survey per contact (plus the default); several surveys can still be sent from the Surveys app.
- Survey officers only see answers of surveys they may access (Odoo's survey rules).
