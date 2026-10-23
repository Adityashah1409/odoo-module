#!/usr/bin/env bash
# Install module(s) on a fresh database and run their tests.
#
# Usage:  tools/run_tests.sh <19.0|20.0> <path/to/odoo/source> <module[,module...]> [extra odoo args]
#
# Database connection comes from DB_HOST / DB_PORT / DB_USER / DB_PASSWORD
# (defaults: localhost / 5432 / odoo / odoo). The database is dropped first.
set -euo pipefail

VERSION="${1:?version (19.0 or 20.0)}"
ODOO="${2:?path to the Odoo source}"
MODULES="${3:?module name(s), comma separated}"
shift 3

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-odoo}"
DB_PASSWORD="${DB_PASSWORD:-odoo}"
DB="test_${VERSION%%.*}_$(echo "$MODULES" | tr ',' '_' | cut -c1-40)"
LOG="$(mktemp)"

PGPASSWORD="$DB_PASSWORD" dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" --if-exists "$DB"

python "$ODOO/odoo-bin" \
  --addons-path="$ODOO/addons,$ODOO/odoo/addons,$REPO/$VERSION" \
  --db_host="$DB_HOST" --db_port="$DB_PORT" --db_user="$DB_USER" --db_password="$DB_PASSWORD" \
  -d "$DB" -i "$MODULES" --test-enable --stop-after-init --log-level=test \
  --test-tags="/$(echo "$MODULES" | sed 's/,/,\//g')" "$@" 2>&1 | tee "$LOG"

echo
echo "== Summary ($VERSION: $MODULES)"
grep -E "odoo.tests.result|tests? (passed|failed)" "$LOG" | tail -3 || true
if grep -qE " (ERROR|CRITICAL) " "$LOG"; then
  echo "FAILED: errors found in the log:"
  grep -E " (ERROR|CRITICAL) " "$LOG" | head -40
  exit 1
fi
echo "OK"
