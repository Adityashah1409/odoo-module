# odoo-module

Odoo backend modules by Aditya, maintained for **Odoo 19.0** and **Odoo 20.0** side by side.

## Repository layout

```
odoo-module/
├── 19.0/                 # addons path for Odoo 19 (one folder per module)
├── 20.0/                 # addons path for Odoo 20 (same modules, ported)
├── docs/                 # one end-to-end guide per module (plan, build, test, deploy)
├── tools/                # helper scripts (test runner, 19 -> 20 porting)
└── .github/workflows/    # CI: installs and tests every module on 19.0 and 20.0
```

Every module lives on its own branch and arrives through its own pull request.
Each PR contains the module for both versions plus its guide in `docs/`.

## Modules

| Module | What it does | Guide |
| --- | --- | --- |
| `my_backend_theme` | Configurable backend theme for Odoo 20 (in progress) | — |
| `cloud_storage_sync` | Folders for attachments, folder rules, and sync to WebDAV / Nextcloud / NAS / local storage | [docs](docs/cloud_storage_sync.md) |
| `shopify_sync` | Shopify connector: products, customers, orders, stock, webhooks | [docs](docs/shopify_sync.md) |
| `fleet_traccar_tracking` | Live GPS positions and trips from a Traccar server on Fleet vehicles | [docs](docs/fleet_traccar_tracking.md) |
| `mrp_bom_import` | Import Bills of Materials from CSV / Excel | [docs](docs/mrp_bom_import.md) |
| `sale_cpq_configurator` | Configure-Price-Quote: guided product configuration with rules and price rules | [docs](docs/sale_cpq_configurator.md) |
| `powerbi_connector` | Push Odoo data to Power BI datasets, or pull it through a secured JSON feed | [docs](docs/powerbi_connector.md) |
| `pos_keyboard_shortcuts` | Configurable keyboard shortcuts for the Point of Sale | [docs](docs/pos_keyboard_shortcuts.md) |
| `pos_product_auto_discount` | Automatic discounts on selected products in the Point of Sale | [docs](docs/pos_product_auto_discount.md) |
| `web_home_screen_designer` | App home screen for the backend with a designer (background, layout, app order) | [docs](docs/web_home_screen_designer.md) |
| `account_invoice_partial_payment` | Allocate one customer/vendor payment across several invoices with partial amounts | [docs](docs/account_invoice_partial_payment.md) |

## Using the modules

Add the folder that matches your Odoo version to the addons path:

```bash
# Odoo 19
./odoo-bin --addons-path=addons,/path/to/odoo-module/19.0 -d mydb -i cloud_storage_sync

# Odoo 20
./odoo-bin --addons-path=addons,/path/to/odoo-module/20.0 -d mydb -i cloud_storage_sync
```

On Odoo.sh, add this repository as a submodule and point the addons path at the matching version folder.

## Running the tests locally

```bash
tools/run_tests.sh 19.0 /path/to/odoo19 cloud_storage_sync
tools/run_tests.sh 20.0 /path/to/odoo20 cloud_storage_sync
```

CI runs the same thing on every pull request (`.github/workflows/odoo-tests.yml`).

## Branches

- `main`: released modules.
- `module/<name>`: one branch per module, merged through a PR.
- `setup/*`: repository tooling.

All modules are LGPL-3 and depend only on Odoo Community.
