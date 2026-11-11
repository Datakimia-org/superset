#!/usr/bin/env bash
# Scan superset-frontend for common 4.x → 6.x migration footguns (Datakimia fork QA).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FE="$ROOT/superset-frontend"
FAIL=0

scan() {
  local label="$1"
  shift
  local matches
  matches="$(rg -n "$@" "$FE" \
    --glob '*.{ts,tsx,js,jsx}' \
    --glob '!**/*.test.*' \
    --glob '!**/*.stories.*' \
    --glob '!**/node_modules/**' 2>/dev/null || true)"
  if [[ -n "$matches" ]]; then
    echo "=== $label ==="
    echo "$matches"
    echo
    FAIL=1
  fi
}

scan "Legacy theme tokens (theme.colors / typography / gridUnit)" \
  'theme\.colors\.|colors\.grayscale|typography\.sizes|typography\.weights|theme\.gridUnit|supersetTheme\.colors'

scan "Removed antd-v5 alias (use antd in Superset 6)" \
  "from 'antd-v5'|from \"antd-v5\""

scan "Broken src/components shims (Menu/Label/Avatar without index — use core)" \
  "from 'src/components/(Menu|Label|Avatar|EmptyState)'"

scan "Removed src/components paths (Modal, Button, DatePicker, Icons default)" \
  "from 'src/components/(Modal|Button|Input|DatePicker|Tooltip|Icons)'"

scan "Renamed Icons (EditAlt, Trash)" \
  'Icons\.(EditAlt|Trash)\b'

scan "Ant Design v4 visible prop on Popover/Modal (prefer open)" \
  '<(ControlPopover|Popover|Modal)[^>]*(visible=|\svisible=)'

if [[ "$FAIL" -eq 0 ]]; then
  echo "No legacy frontend patterns matched (non-test sources)."
fi
exit "$FAIL"
