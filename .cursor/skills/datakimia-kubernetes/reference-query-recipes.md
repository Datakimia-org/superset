# Query recipes (GKE / Superset)

Use after resolving **cluster + env** via `product-portal-config` (`list-environments.sh`) and pod via `resolve-superset-pod.sh`.

Non-secret env keys for an environment: `../product-portal-config/{lo|hi}/<env_name>/superset.yaml` (and `frontend.yaml` / `backend.yaml` for Portal).

## Image and rollout

```bash
NS=<namespace>
POD=$(./.cursor/skills/datakimia-kubernetes/scripts/resolve-superset-pod.sh "$NS")
kubectl get pod -n "$NS" "$POD" -o jsonpath='{.spec.containers[0].image}{"\n"}'
kubectl get pod -n "$NS" "$POD" -o jsonpath='{.status.containerStatuses[0].imageID}{"\n"}'
kubectl rollout status deployment -n "$NS" -l app.kubernetes.io/name=superset
```

## App version (one of many checks — not the primary skill purpose)

```bash
kubectl exec -n "$NS" "$POD" -- cat /app/superset/static/version_info.json
kubectl exec -n "$NS" "$POD" -- python -c "
from superset.app import create_app
a = create_app()
print('VERSION_STRING', a.config.get('VERSION_STRING'))
print('VERSION_SHA', a.config.get('VERSION_SHA'))
"
```

## Logs

```bash
kubectl logs -n "$NS" "$POD" --tail=200
kubectl logs -n "$NS" "$POD" -c superset --tail=200   # if multi-container
POD_W=$(./.cursor/skills/datakimia-kubernetes/scripts/resolve-superset-pod.sh "$NS" worker)
kubectl logs -n "$NS" "$POD_W" --tail=200
```

## Config snippet inside pod

```bash
kubectl exec -n "$NS" "$POD" -- python -c "
from superset.app import create_app
a = create_app()
for k in ('WEBDRIVER_TYPE','PLAYWRIGHT_REPORTS_AND_THUMBNAILS','SCREENSHOT_TILED_ENABLED'):
    print(k, a.config.get(k))
"
```

## Discover namespaces (first-time env)

```bash
kubectl config current-context
kubectl get ns | rg '^ephemeral-'
kubectl get pods -n <namespace>
kubectl get deploy,svc,ingress -n <namespace>
```

After discovery, add or update an entry in `environments.yaml`.
