#!/usr/bin/env bash
# Re-apply thumbnail hotfixes to a running GKE ephemeral namespace after a
# deploy wipes image-layer /app/config changes (until the PR image ships).
#
# Covers:
#   - Error + diagnostic PNG on Playwright/Selenium capture failure
#   - No sticky Pending/Computing poison; ERROR(+img) / UPDATED terminal states
#   - Celery rate_limit for cache_*_thumbnail (per-worker)
#
# Usage:
#   ./scripts/k8s/thumbnail_runtime_hotfix/apply_ephemeral.sh
#   NS=ephemeral-migration-superset-version CONTEXT=GKE-LO ./scripts/k8s/thumbnail_runtime_hotfix/apply_ephemeral.sh
#
# Requires: kubectl authenticated to the cluster; gcloud auth if using GKE.
set -euo pipefail

NS="${NS:-ephemeral-migration-superset-version}"
CONTEXT="${CONTEXT:-GKE-LO}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
HOTFIX_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

HOTFIX_PY="${HOTFIX_DIR}/thumbnail_cache_hotfix.py"
PATCH_PY="${HOTFIX_DIR}/patch_superset_config.py"
WEBDRIVER_SRC="${ROOT}/superset/utils/webdriver.py"

if [[ ! -f "$HOTFIX_PY" || ! -f "$PATCH_PY" || ! -f "$WEBDRIVER_SRC" ]]; then
  echo "Missing hotfix assets under ${HOTFIX_DIR} or ${WEBDRIVER_SRC}" >&2
  exit 1
fi

kubectl() {
  command kubectl --context "$CONTEXT" "$@"
}

echo "Context=${CONTEXT} Namespace=${NS}"

mapfile -t WEB_PODS < <(kubectl get pods -n "$NS" -l app=superset-datakimia -o jsonpath='{.items[*].metadata.name}' 2>/dev/null | tr ' ' '\n' | grep -E '^superset-datakimia-[a-z0-9]+-[a-z0-9]+$' || true)
# Fallback: name-prefix match (Datakimia chart labels vary)
if [[ ${#WEB_PODS[@]} -eq 0 ]]; then
  mapfile -t WEB_PODS < <(kubectl get pods -n "$NS" --no-headers -o custom-columns=NAME:.metadata.name \
    | awk '/^superset-datakimia-[a-f0-9]+-/ && $0 !~ /worker|postgresql|redis|init|celerybeat/ {print}')
fi
mapfile -t WORKER_PODS < <(kubectl get pods -n "$NS" --no-headers -o custom-columns=NAME:.metadata.name \
  | awk '/^superset-datakimia-worker-/ {print}')

if [[ ${#WEB_PODS[@]} -eq 0 || ${#WORKER_PODS[@]} -eq 0 ]]; then
  echo "Could not find web/worker pods in ${NS}" >&2
  kubectl get pods -n "$NS" >&2 || true
  exit 1
fi

echo "Web pods: ${WEB_PODS[*]}"
echo "Worker pods: ${WORKER_PODS[*]}"

deploy_files() {
  local pod="$1"
  echo "--- files -> ${pod}"
  kubectl cp -n "$NS" -c "superset" "$HOTFIX_PY" "${pod}:/app/config/thumbnail_cache_hotfix.py"
  kubectl cp -n "$NS" -c "superset" "$WEBDRIVER_SRC" "${pod}:/app/config/_hotfix_webdriver.py"
  kubectl cp -n "$NS" -c "superset" "$PATCH_PY" "${pod}:/tmp/patch_superset_config.py"
  kubectl exec -n "$NS" -c "superset" "$pod" -- python /tmp/patch_superset_config.py
}

for pod in "${WEB_PODS[@]}"; do
  deploy_files "$pod"
  kubectl exec -n "$NS" -c "superset" "$pod" -- sh -c '
    GPID=$(pgrep -f "/app/.venv/bin/gunicorn" | head -1)
    echo "HUP gunicorn pid=$GPID"
    kill -HUP "$GPID"
  '
done

for pod in "${WORKER_PODS[@]}"; do
  deploy_files "$pod"
  kubectl exec -n "$NS" -c "superset" "$pod" -- sh -c '
    set -e
    MAIN=$(pgrep -P 1 -f "celery --app=superset.tasks.celery_app:app worker" | head -1 || true)
    if [ -n "$MAIN" ]; then
      for cpid in $(pgrep -P "$MAIN" || true); do
        kill -STOP "$cpid" 2>/dev/null || true
      done
      echo "Stopped original celery children under main=$MAIN"
    fi
    if [ -f /tmp/hotfix-celery.pid ]; then
      kill "$(cat /tmp/hotfix-celery.pid)" 2>/dev/null || true
      sleep 1
    fi
    nohup /app/.venv/bin/celery --app=superset.tasks.celery_app:app worker \
      --concurrency=2 -n "hotfix@%h" --loglevel=INFO \
      > /tmp/hotfix-celery.log 2>&1 &
    echo $! > /tmp/hotfix-celery.pid
    for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
      if grep -q "error+png\|thumbnail_cache_hotfix applied" /tmp/hotfix-celery.log 2>/dev/null; then
        break
      fi
      sleep 2
    done
    grep -E "error\+png|Playwright/Selenium|thumbnail_cache_hotfix|Traceback" /tmp/hotfix-celery.log | tail -15 || true
    echo "hotfix_celery pid=$(cat /tmp/hotfix-celery.pid) alive=$(kill -0 $(cat /tmp/hotfix-celery.pid) 2>/dev/null && echo yes || echo no)"
  '
done

echo
echo "Done. Hotfix is live until pods restart."
echo "Verify logs for: thumbnail_cache_hotfix applied (error+png)"
echo "Rate limits: cache_dashboard_thumbnail=1/m, cache_chart_thumbnail=2/m (per worker)."
