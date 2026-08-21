# Superset 6.1 — Migration & Product Integration (conceptual / stakeholders)

**Audience:** client / stakeholders  
**Level:** conceptual overview — not an implementation plan.
**Purpose:** coarse view of the work to move from our Superset **4.1.1** fork to **Superset 6.1**. We do it in **two stages** (4.1.1 → **5**, then 5 → **6.1**) to isolate blast radius — not because the metadata upgrades require a stop on 5. Production target is **6.1**; 5 is a **staging waypoint**, not a production park. MCP is productized in stage 2 (it **ships in 6.1**; it is not present on 5).  
**Not in this doc:** technical design or implementation options.

Rough complexity per area: **S** (small) · **M** (medium) · **L** (large)

Datakimia runs **per-client** Superset deployments. Each hop is a **pilot client → fleet** rollout: N metadata upgrades, N config diffs, N acceptance passes, N cutover windows.

---

## 0. Before Stage 1 — bring the fork to 4.1.4 — **S**

The fork sits on **4.1.1**. **4.1.2, 4.1.3 and 4.1.4** followed in the same line and are mostly security work. That exposure is live today and is **independent of the migration**.

Material for this product includes: CVE fixes; harder validation when importing dashboards/charts/datasets; and, in embedded mode, **no longer returning the generated query** to guest users (on 4.1.1 that is SQL disclosure to client end users).

This is a patch rebase, not a major upgrade. Anything the Portal calls in Superset must be re-checked after it (token/cookie handling changed). Do this **now**, not during Stage 1.

---

## Stage 1 — Land on Superset 5 (waypoint)

Get the fork and the current product working on Superset 5 in **staging**. There is **no MCP to enable** on 5 — the service does not exist in that release. Do not cut production over to 5: upstream support is already on the 6.x line.

### 1.1 Migrate Superset from 4.1.4 to 5 — **L**

Bring our fork onto the Superset 5 baseline. This includes:

- Moving the codebase and dependencies onto Superset 5
- Upgrading the Superset metadata database (time this on a production-sized copy; several models gain new identifiers)
- Rebuilding and validating images / local and deployed environments (runtime and frontend build change in this hop)
- Handling upstream breaking changes that affect how Superset runs

**Why it matters:** stage 2 is only safe if the product already works on 5 in staging.

### 1.2 Keep login and Portal↔Superset trust working — **L**

Users sign in via Google / Microsoft / Auth0 and the Portal talks to Superset on their behalf. After the upgrade we must re-validate that login, session continuity, and Portal→Superset access still work end to end.

### 1.3 Roles, permissions, and embedded “guest” access — **M–L**

We use custom roles (including Guest for embedded dashboards). These must be re-checked on Superset 5 so viewers still see only what they should.

**Drill to Detail** becomes always-on in the BI UI in 5 (the old on/off switch is retired). In this stage it is a logged-in-user concern, not yet an embedded one. Confirm it does not leak rows the tenant should not see.

### 1.4 Embedded dashboards in the Portal — **M**

Dashboards shown inside the Portal must keep loading correctly for normal (non-admin) users, including refresh of temporary access. The Portal embed library must be upgraded **in lockstep** with Superset.

### 1.5 Portal features that call Superset APIs — **M**

Portal screens that list dashboards, manage users/roles, show thumbnails, etc. depend on Superset APIs. Those integrations need a regression pass and likely small fixes where responses or behavior changed.

Concrete 5.0 deltas to check: older (pre-v1) dashboard routes are gone; the dashboard **list** payload no longer includes layout/CSS/metadata fields; data-upload endpoints and permissions changed.

### 1.6 Our custom Superset changes (fork features) — **L** (depends on inventory)

Beyond stock Superset we carry custom behavior (notably saved filter sets, UI tweaks, caching, BigQuery-related patches). For each: **re-apply on 5**, **replace with a simpler approach**, or **drop**.

**Filter sets** are not a small custom add-on. Upstream **deleted** the feature in 4.0 as unmaintained and buggy, and said any successor should be rebuilt from scratch. This fork put it back. Default position: **drop or replace**. Keep it only if there is an explicit client contractual requirement. Decide **in this stage** — carrying it through two upgrades costs more.

Sizing 1.6/2.5 honestly requires a **diff of the fork against upstream 4.1.1**, grouped into: already adopted upstream (drop); now doable as config / theme / extension (replace); must still be carried. Until that inventory exists, **L** is a placeholder.

### 1.7 Generated SQL, virtual datasets, and row-level security — **M–L**

On 5, how charts become SQL already changes (filters are pushed into virtual datasets). That affects BigQuery cost, cache, and tenancy.

For a representative set of client charts (especially virtual-dataset + RLS): capture **generated SQL and returned row counts** before and after the hop, and diff. Acceptance is not “the dashboard loads.”

(The larger SQL-engine rewrite lands in stage 2.)

### 1.8 BigQuery catalogs and permissions — **M**

In BigQuery, a catalog is a GCP project. 5 starts treating catalogs as first-class (cache keys, saved queries, credentials). Plan a **permission-sync per client** and expect cache invalidation.

### 1.9 Thumbnails, downloads, and scheduled reports — **M**

Screenshots move off the old browser stack toward Playwright, run as background work, and use a different “who takes the picture” model. Anything the Portal relies on — thumbnails, PDF/PNG, scheduled reports — must be re-proven on 5.

### 1.10 Environments, images, and the 5 waypoint — **M**

New images, env vars, secrets. **5 is staging-only.** Roll out **pilot client → fleet**.

Rollback is **restore from snapshot**, plus a YAML export of dashboards / charts / datasets before the hop. There is **no supported metadata-DB downgrade**. Promoting assets between environments also changes (stricter import validation, encrypted fields) — regression-test import/export, do not assume it survives untouched.

First dashboard loads after cutover will be **cold cache**; say so to clients.

### 1.11 Product acceptance for stage 1 — **M**

End-to-end on 5: login, roles, catalog, embed, user admin, retained custom features, **Spanish UI/locale**, chart-render audit (especially time-comparison and remaining legacy chart types). **Event Flow** and **Sankey Loop** charts are gone with no replacement — audit client dashboards before this hop.

---

## Stage 2 — Move from 5 to 6.1 (production target)

Includes the **6.0** platform/UI overhaul and productizing **MCP**, which **ships in 6.1**.

### 2.1 Migrate Superset from 5 to 6.1 — **L**

Bring the 5-based fork onto **6.1** (this jump includes 6.0). This includes:

- Moving the codebase and dependencies onto 6.1
- Upgrading the Superset metadata database again (time this on a production-sized copy; security/login tables move with two framework upgrades)
- Rebuilding and validating images / environments (frontend toolchain moves again)
- Handling upstream breaking changes from 6.0 and 6.1 — including the new look-and-feel / theming, branding moving into the theme, and **all cached thumbnails and dashboard/chart digests rebuilding** (hash change)

**Why it matters:** this is the production runtime; MCP as a product capability is built here.

### 2.2 Enable and productize Superset MCP — **L**

MCP **ships in 6.1** (optional extra process; no extra DB migration). On 5 there is nothing to turn on. Turning it into a usable product capability means:

- Deciding how **Portal-authenticated users / agents** authenticate into MCP
- Deploying and securing the MCP service in our environments (own process)
- Making sure each AI action runs as the right **Superset user** (permissions and data access still apply)
- Connecting our product / AI clients to that service
- Adjusting or retiring the temporary MCP-related bridge we have in the Portal today
- Confirming we can see usage and failures (upstream already records MCP calls in the action log)

**Constraint (product, not a later surprise):** MCP binds to a real user in Superset. **Embedded guest tokens are not an MCP login.** Embedded viewers do not get MCP. Dev-only “run as a fixed user, no auth” must never reach a client environment.

**Why it matters:** without this work MCP is not a product feature, only an unused upstream capability.

### 2.3 Re-validate login, roles, and embed — **L**

Login, session continuity, custom roles (including Guest), and embedded dashboards must be re-checked after the 6.0 UI/platform changes. We already use OAuth (Google / Microsoft / Auth0); this is regression, not a change of identity provider. Custom role names must be audited — some row-level-security admin permissions were removed.

**Embedded drill-down is a security change:** 6.0 turns **Drill to Detail / Drill By** on for embedded dashboards. For a multi-tenant embed this can be a per-client row leak. If we do not want it, the Guest / embed roles must not have those permissions. Treat this as a named checklist item, not a side effect.

Upgrade the Portal embed library again. Two behaviours that can change the iframe with no config on our side: how the iframe sends referrer information, and the default embed theme (light, not “follow the OS”).

### 2.4 Portal features that call Superset APIs — **M**

Catalog, user/role admin, thumbnails, and similar Portal screens need another regression pass on 6.1 (role admin moved to the frontend in 6.0). Old share-by-link shortcuts are **permalinks only**. If we manage datasets as files, export filenames now include the dataset id.

### 2.5 Custom fork features that survived stage 1 — **M–L**

Re-apply, replace, or drop whatever custom behavior we kept on 5. UI tweaks are more expensive after the 6.0 redesign (old colour tokens will not build). Filter sets only appear here if we chose to keep them in stage 1.

Also ask, per leftover custom feature: **rebuild as an upstream extension or a database-managed theme** instead of carrying a fork patch (see Opportunities below).

### 2.6 SQL engine and row-level security — **L**

This is the **highest-risk backend item** in the whole migration.

6.0 **replaces the SQL parser** and **reimplements row-level security** on it. 6.1 then fixes **double RLS on virtual datasets in embedded mode** — a real defect on 6.0 in the configuration we use. Stopping on 6.0 is not attractive.

Same acceptance as 1.7, heavier: per-client **generated SQL + row counts** for known tenants, especially embedded + virtual datasets. If we filter tenants in SQL templates, re-test that path — template rendering now happens before the new parser runs.

### 2.7 Theming and white-label — **M–L**

6.0 **breaks** the old theme-override and custom-CSS approach (new design system, new class names). Branding and fonts move into the theme. Any fork UI that assumed the old look will not carry over.

Themes become **import/export database objects** with an admin UI. That may be a better per-client white-label mechanism than fork-level CSS — evaluate during 2.5 rather than blindly porting styles.

### 2.8 Thumbnails, downloads, and scheduled reports — **M**

Continue the screenshot-pipeline work: Chromium/Playwright in images and workers, tiled screenshots for large dashboards, and a full thumbnail cache rebuild after the 6.1 hash change.

### 2.9 Environments, MCP topology, and cutover to 6.1 — **M**

New images, env vars, deploy topology (including the MCP process), secrets. **Pilot → fleet** into production. Same rollback rule as 1.10: **snapshot restore + YAML asset export**, no DB downgrade. Re-test asset import/export. Warn clients about **cold cache** after cutover.

### 2.10 Security configuration for embed, SSO, and MCP — **M**

Confirm that login, embedded dashboards (including drill-down permissions), and the MCP access model are configured correctly for 6.1. Validate in staging before production.

This is a **configuration + validation** step aligned with the upgrade, not a separate security project.

### 2.11 Product acceptance for stage 2 — **M**

Everything from stage 1, plus: 6.0 look-and-feel, embed theme/referrer behaviour, drill-down allow/deny in embed, RLS/SQL diffs, MCP success **and** denial paths, **Spanish UI/locale**.

### 2.12 Docs and client communication — **S–M**

Update internal runbooks and tell stakeholders what changes for them: new UI (including filter bar / auto-refresh / Explore behaviour), any dropped custom feature (filter sets), MCP available only to Portal users (not embed guests), cold cache after cutover, gone chart types.

---

## Opportunities (may shrink the fork)

These are not extra projects; they are options to **stop carrying fork code**:

- **Extensions (mature in 6.1):** some UI/SQL Lab customizations can be extensions instead of a fork.
- **Database-managed themes:** per-client white-label as an importable asset.
- **User groups (6.0):** roles on groups rather than every individual user — useful at fleet scale.
- **New SQL template helpers** (current user roles / RLS rules): possible replacement for some custom tenancy logic — only after 2.6 passes.

---

## Suggested order (high level)

**Now**

1. Rebase the fork to **4.1.4** (security)
2. Inventory the fork against upstream 4.1.1 (needed to size 1.6 / 2.5)

**Stage 1 (staging waypoint on 5)**

1. Migrate fork to Superset 5
2. Restore login / roles / embed; upgrade the Portal embed library
3. Portal catalog & admin regressions
4. Generated SQL / virtual datasets / RLS sample diffs; BigQuery catalog permission sync
5. Decide fate of heavy custom fork features (filter sets: default drop/replace)
6. Thumbnails / reports; snapshot + YAML; **do not** cut production to 5
7. Acceptance on 5 (including Spanish and chart-type audit)

**Stage 2 (production on 6.1)**

1. Migrate 5 → 6.1
2. Restore login / roles / embed after the 6.0 UI change; **embed drill-down permissions**; embed library again
3. SQL engine + RLS revalidation (the high-risk hop)
4. Theming / white-label (port, or replace with managed themes)
5. Portal catalog & admin regressions
6. MCP as a product capability (Portal users only)
7. Re-apply remaining fork features (or rebuild as extension/theme)
8. Embed / SSO / MCP config validation + fleet cutover + acceptance
