#!/usr/bin/env bash
# Copy a module from 19.0/ to 20.0/ and run Odoo 20's own code upgrader on it
# (ir.access CSV, icons, OWL 3, t-call, search filters, ...).
#
# Usage:  tools/port_19_to_20.sh <module> <path/to/odoo20/source>
#
# Review the diff afterwards and run tools/run_tests.sh 20.0 ... on the result.
set -euo pipefail

MODULE="${1:?module name}"
ODOO20="${2:?path to the Odoo 20 source}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

rm -rf "$REPO/20.0/$MODULE"
cp -r "$REPO/19.0/$MODULE" "$REPO/20.0/$MODULE"

# Bump the manifest version prefix 19.0.x.y.z -> 20.0.x.y.z
sed -i -E "s/'version': '19\.0\./'version': '20.0./" "$REPO/20.0/$MODULE/__manifest__.py"

cd "$ODOO20"
# Two passes: when the ir.access script deletes a security.xml that only held rules,
# later scripts crash on the deleted file if everything runs in one pass.
for range in "19.0 19.4" "19.5 20.0"; do
  set -- $range
  python odoo-bin upgrade_code --from "$1" --to "$2" \
    --addons-path="$ODOO20/addons,$ODOO20/odoo/addons,$REPO/20.0" \
    --glob "$MODULE/**/*" || true   # exits 1 when files were rewritten
done

# Fixes not (yet) covered by upgrade_code
python "$SCRIPT_DIR/post_port_20.py" "$REPO/20.0/$MODULE"

echo "Ported $MODULE to $REPO/20.0/$MODULE"
