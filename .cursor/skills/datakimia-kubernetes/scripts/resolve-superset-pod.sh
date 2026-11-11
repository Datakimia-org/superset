#!/usr/bin/env bash
# Resolve Superset app pod name in a namespace (Datakimia GKE).
set -euo pipefail

NS="${1:?Usage: $0 <namespace> [superset_app|worker]}"
ROLE="${2:-superset_app}"

case "$ROLE" in
  superset_app)
    if kubectl get pods -n "$NS" -l app.kubernetes.io/name=superset -o name 2>/dev/null | head -1 | grep -q .; then
      kubectl get pods -n "$NS" -l app.kubernetes.io/name=superset -o jsonpath='{.items[0].metadata.name}'
      exit 0
    fi
    kubectl get pods -n "$NS" --no-headers 2>/dev/null \
      | awk '/^superset-datakimia-/ && !/init|worker|redis|postgres/ {print $1; exit}'
    ;;
  worker)
    kubectl get pods -n "$NS" --no-headers 2>/dev/null \
      | awk '/^superset-datakimia-worker-/ {print $1; exit}'
    ;;
  *)
    echo "Unknown role: $ROLE" >&2
    exit 1
    ;;
esac
