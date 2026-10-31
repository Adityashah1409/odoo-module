# Short URLs & QR Codes (`short_urls`)

Short links (`/s/<code>`) with QR codes for **Odoo 19.0 / 20.0** websites:
- generated or custom codes;
- expiry dates;
- marketing channels with UTM tags;
- click statistics;
- automatic creation rules;
- a *Short URLs of this page* dialog in the website editor;
- two snippets.

The code lives in:
- `19.0/short_urls/`;
- `20.0/short_urls/`.

---

## 1. Planning

### 1.1 Goal

Marketing prints QR codes on flyers, posts links on social networks and in newsletters. Long Odoo URLs are ugly
and do not tell which channel brought the visit. The module gives short, memorable links on the company's own
domain, QR codes ready to print, and click counts per link and channel, without an external shortener.

### 1.2 Requirements

| # | Requirement |
| --- | --- |
| R1 | `/s/<code>` redirects to a page of the site or any http(s) address |
| R2 | Codes generated (random or sequential, configurable length) or chosen by hand; unique; editable |
| R3 | QR code per link: on screen and as PNG |
| R4 | Expiry date and archive; expired links show a clear page |
| R5 | Channel and campaign per link, optional UTM tags on the redirect |
| R6 | Click statistics without storing personal data; bots excluded |
| R7 | Links created automatically for pages (and other website records) |
| R8 | Manage the links of the page being edited, from the website editor |
| R9 | Snippets showing the page's short link and QR code |
| R10 | Multi-website, editor / designer rights, Odoo 19 and 20 |

### 1.3 Scope (v1)

In: everything above.

Out:
- custom prefix instead of `/s/` (the route is fixed);
- per-link password;
- A/B redirects;
- import from other shorteners.

### 1.4 Roles

| Role | Can |
| --- | --- |
| Website restricted editor | Create and edit links, see clicks, channels and rules |
| Website designer | Delete links, manage channels and rules, settings |
| Visitor | Follow links, see snippets (snippets never create links for visitors) |

### 1.5 Acceptance criteria

- `/s/spring` answers 302 to its target; a click line is added.
- A link preview (Facebook, WhatsApp…) is recorded as a bot and not counted.
- With *Add UTM tags*, the target gets `utm_source`, `utm_medium`, `utm_campaign`, keeping its own parameters.
- An expired code answers 404 with "This link is no longer available".
- Applying a rule twice creates no duplicate.

### 1.6 Screenshots

`static/description/screenshots/` in each version: page dialog, snippets, links, links by target, link form, clicks
graph and pivot, rule, channels, settings, expired page.

---

## 2. Architecture

```
Visitor ── GET /s/<code> ──► ShortUrlController.short_url_redirect
                               ├─ short.url._find_for_redirect(code, website)   website link first, then global
                               ├─ state != valid → 404 "link no longer available"
                               ├─ short.url.click._record(): network /24, device, browser, country, referrer, bot
                               └─ 302 → short.url._redirect_url()                 (+ UTM tags)

Backend     short.url (form, list, QR) ─ short.url.channel ─ short.url.rule (daily job)
Editor      Site › This page › Short URLs → website_custom_menus → PageShortUrlsDialog
               → short.url.page_links() / create_for_page()
Page        snippets s_short_url / s_short_url_qr → interaction → /short_urls/page_link
               → link of the page (created only for designers)
QR          /short_urls/qr/<code>.png → qrcode library (PNG, 100–1000 px)
```

### 2.1 Design decisions

- **Codes are unique in the whole database**, not per website: a code never means two things, and a link without
  website works everywhere.
- **Random codes avoid ambiguous characters** (0/O, 1/l/I), important for printed codes typed by hand.
- **QR codes with the `qrcode` library** (an Odoo requirement) rather than the report barcode engine, which needs
  an optional ReportLab backend for PNG.
- **Clicks are counted from the click lines** (stored, recomputed per link) so the list can sort on clicks; bots
  stay in the lines (useful to see previews) but not in the counts.
- **Privacy**: no full IP, no cookie; country comes from Odoo's GeoIP when configured.
- **Same page, several links**: the page dialog and the snippets look for the relative path and the absolute URL
  of the site, so links made either way are found.
- **Editor integration** through Odoo's `website_custom_menus` registry: the menu item appears under *Site ›
  This page* and opens a dialog for the current path.

---

## 3. Development

```
short_urls/
├── models/
│   ├── short_url.py          links, channels, validation, state, QR, redirect URL, page helpers
│   ├── short_url_click.py    clicks, user-agent parsing, IP anonymisation
│   ├── short_url_rule.py     automatic rules
│   ├── website.py            settings, code generator, base URL, current website
│   └── res_config_settings.py
├── controllers/main.py       /s/<code>, QR PNG, snippet JSON route
├── views/                    backend views, settings, menus, 404 page, snippets
├── data/                     sequence, daily job, default channels
├── static/src/backend/       page dialog (editor)
├── static/src/snippets/      snippet interaction
└── tests/                    11 tests + tour
```

**Try it in a shell**

```python
link = env['short.url'].create({'target_url': '/contactus', 'token': 'hello',
                                'channel_id': env.ref('short_urls.channel_print').id, 'add_utm': True})
link.short_url, link._redirect_url()
env['short.url.click']._record(link, link.website_id, ip='81.2.3.4', user_agent='Mozilla/5.0 (iPhone) Mobile')
link.click_count
```

**Extend**
- Another source of automatic links: any model with a `website_url` field can be chosen in a rule.
- More click data: override `short.url.click._record()`.

---

## 4. Testing

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 short_urls
tools/run_tests.sh 20.0 /path/to/odoo20 short_urls
```

| Test | Covers |
| --- | --- |
| `test_generated_tokens` | random length / alphabet, sequential codes |
| `test_validation` | invalid codes and targets, duplicates, trimming |
| `test_redirect_and_clicks` | 302, device / browser / referrer / network, bots not counted |
| `test_utm_tags` | UTM values from the channel and campaign, existing parameters kept |
| `test_expired_archived_unknown_and_global` | 404 page, state search, global vs website links |
| `test_qr_code` | form image, PNG route, download name, unknown code |
| `test_rules` | filter, published only, validity, idempotence, cron, invalid filter |
| `test_page_dialog_methods` | list and create for a page, default validity, absolute targets |
| `test_snippet_route_and_access` | visitors never create links, designers do; editor / portal rights |
| `test_regenerate_and_views` | new code, old code dead |
| `test_tour_snippet` | the page shows the short link and QR code |

**Manual test**
1. Open a page in the editor, *Site › This page › Short URLs*, create `/s/test` with the *Print* channel.
2. Scan the QR code with a phone: the page opens; the click appears in *Reporting › Short URL Clicks* as mobile.
3. Drop the *Short URL* and *Short URL QR* snippets on the page and save.

---

## 5. Deployment: dev → staging → production

1. **Dev:** run the tests; set the website domain to the development host so QR codes point to it.
2. **Staging:**
   - after restoring production, short URLs point to the production domain (they use the website domain):
     change the staging website domain to test QR codes;
   - check the reverse proxy forwards `/s/` and `/short_urls/` to Odoo.
3. **Production:**
   - set the final website domain **before** printing QR codes;
   - choose the code style (random for public links, sequential for internal inventories);
   - create the channels used by marketing; add rules if every page or product needs a QR code.
4. **Performance:** a redirect costs one indexed search and one insert. The click table grows with traffic; it is
   indexed on date, link and bot flag. Archive or delete old clicks if needed (designers can delete them).
5. **Monitoring:** *Short URL Clicks* graph; *Expired* filter on links before a campaign; server log for 404s on
   `/s/`.
6. **Rollback:** uninstalling removes the links and clicks; printed QR codes stop working (404). Export the list
   first if they must be recreated elsewhere.

---

## 6. Odoo 19 vs Odoo 20

| Topic | 19.0 | 20.0 |
| --- | --- | --- |
| Current website | `website.get_current_website()` | `env.website` (model moved to `base`), default website as fallback |
| Binary field values | base64 | base64 string (bytes refused) |
| Access rights | `ir.model.access.csv` + record rule | `ir.access.csv` |
| Editor dialog | OWL 2 (`useState`, `static props`) | OWL 3 (`proxy`, `useProps`, `this.` in templates) |
| Icons | Font Awesome | Odoo 20 icon set |

---

## 7. Known limitations

- The prefix is always `/s/`.
- Codes are case-sensitive (`Spring` ≠ `spring`).
- Country statistics need Odoo's GeoIP database.
- Bots are detected from the user agent; unknown bots may be counted.
- Links point to the website domain: changing the domain later breaks printed QR codes unless the old domain
  still redirects to Odoo.
