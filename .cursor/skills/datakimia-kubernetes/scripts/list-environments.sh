#!/usr/bin/env bash
# List Portal/Superset environments from product-portal-config (source of truth).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SUPERSET_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
CONFIG_DIR="${PORTAL_CONFIG_DIR:-$SUPERSET_ROOT/../product-portal-config}"

if [[ ! -d "$CONFIG_DIR" ]]; then
  echo "product-portal-config not found at: $CONFIG_DIR" >&2
  echo "Clone sibling repo or set PORTAL_CONFIG_DIR" >&2
  exit 1
fi

echo "config_dir: $CONFIG_DIR"
echo "---"

for cluster in lo hi; do
  cluster_dir="$CONFIG_DIR/$cluster"
  [[ -d "$cluster_dir" ]] || continue
  for env_dir in "$cluster_dir"/*; do
    [[ -d "$env_dir" ]] || continue
    name="$(basename "$env_dir")"
    has_superset=""
    [[ -f "$env_dir/superset.yaml" ]] && has_superset="superset"
    has_portal=""
    [[ -f "$env_dir/frontend.yaml" && -f "$env_dir/backend.yaml" ]] && has_portal="portal"
    printf '%s\t%s\tnamespace=%s\tcomponents=%s\n' "$cluster" "$name" "$name" "${has_superset:+$has_superset }${has_portal}"
  done
done | sort -t$'\t' -k1,1 -k2,2
