---
name: datakimia-kubernetes
description: Connects to Datakimia GKE Kubernetes clusters using product-portal-config as the environment catalog, resolves namespaces/pods for deployed Superset stacks, and runs kubectl logs/exec queries. Use when the user mentions kubectl, GKE, GKE-LO, GKE-HI, ephemeral, portal-registry, product-portal-config, namespace, pods, or remote environment debug.
---

# Datakimia Kubernetes environments

Generic workflow for **connecting** and **querying** deployed Portal + Superset stacks. Version checks are one optional recipe — see [reference-query-recipes.md](reference-query-recipes.md).

## When to use

- List or pick a **deployed environment**
- Debug **ephemeral**, **clientx**, preprod, etc. on GKE
- **Exec**, **logs**, image digest, non-secret config in pods
- First kubectl session for an env → optional **`runtime_cache`** in [environments.yaml](environments.yaml)

## Prerequisites (human machine)

```bash
gcloud auth login
kubectl config use-context GKE-LO   # or GKE-HI — see environments.yaml clusters
kubectl config current-context
```

Clone layout (sibling repos under `datakimia/`):

```
datakimia/
  superset/                 # this repo
  product-portal-config/    # all environments (source of truth)
  devops/                   # helm deploy, certs
```

Non-interactive agents cannot refresh expired gcloud tokens — ask the user to re-auth if kubectl fails.

## Step 1 — Resolve environment (product-portal-config)

**All deployed environments** are defined in the sibling repo **`product-portal-config`**, not hand-maintained in this skill.

From superset repo root:

```bash
./.cursor/skills/datakimia-kubernetes/scripts/list-environments.sh
```

Output columns: `cluster` (`lo`|`hi`), `env_name`, `namespace=<env_name>`, components (`superset`, `portal`).

| Cluster | Kubectl context | Config path |
|---------|-----------------|-------------|
| `lo` | `GKE-LO` | `../product-portal-config/lo/<env_name>/` |
| `hi` | `GKE-HI` | `../product-portal-config/hi/<env_name>/` |

**Namespace = folder name** (e.g. `ephemeral-migration-superset-version`, `clientx`, `preprod-payfacto`).

Per-env files (non-secret keys only; values in GCP Secret Manager):

- `superset.yaml`, `frontend.yaml`, `backend.yaml`
- `*-secrets.yaml` — secret **names**, not values

Override config location: `export PORTAL_CONFIG_DIR=/path/to/product-portal-config`

Read [environments.yaml](environments.yaml) for cluster defaults, ephemeral image tag rules, and `runtime_cache`.

**New env not in list?** It may not be merged in `product-portal-config` yet — see `devops/helm/scripts/environments/create_new_environment.sh` in the devops repo.

## Step 2 — Select cluster context

```bash
kubectl config use-context GKE-LO   # or GKE-HI from Step 1
NS=<env_name>
kubectl get pods -n "$NS" -o wide
```

## Step 3 — Resolve Superset pod

```bash
POD=$(./.cursor/skills/datakimia-kubernetes/scripts/resolve-superset-pod.sh "$NS")
echo "$POD"
```

Second arg: `superset_app` (default) or `worker`.

## Step 4 — Run queries

Recipes: [reference-query-recipes.md](reference-query-recipes.md). Match the user’s question; do not default to version-only checks.

## Ephemeral git branch ↔ namespace

Superset CI (`.github/workflows/docker-build-push.yml` on `ephemeral/**`):

- Branch `ephemeral/migration-superset-version` → image tag `ephemeral-migration-superset-version`
- Namespace usually matches slug: `ephemeral-migration-superset-version` (confirm in `product-portal-config/lo/`)

## Registry maintenance (runtime only)

Do **not** duplicate the environment catalog in `environments.yaml`.

When kubectl reveals useful **runtime** facts (ingress host, odd pod prefix, last verified image digest):

1. Add under `runtime_cache.<env_name>` in **environments.yaml** with `last_discovered` (ISO date)
2. Never store secrets or secret values

If a **new** environment was created in ops, it belongs in **`product-portal-config`** (human/PR), not only in the skill.

## Typical stack (reference)

| Pod pattern | Role |
|-------------|------|
| `superset-datakimia-*` | Superset app |
| `superset-datakimia-worker-*` | Celery worker |
| `frontend-deployment-*` | Portal frontend |
| `backend-deployment-*` | Portal backend |

Superset “About” version comes from the **superset app** pod.

## Related

- Portal config README: `../product-portal-config/README.md`
- Before pushing code fixes: **`.cursor/rules/pre-push-pipeline.mdc`**
