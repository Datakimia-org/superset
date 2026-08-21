# Superset 5 — Migration & Product Integration

**Audience:** client / stakeholders  
**Purpose:** coarse view of the work to move from Superset **4.1.1** (our fork) to **Superset 5**, and to keep Portal + BI + MCP working as a product.  
**Not in this doc:** technical design or implementation options.

Rough complexity per area: **S** (small) · **M** (medium) · **L** (large)

---

## 1. Migrate Superset from 4.1.1 to 5 — **L**

Bring our Superset fork onto the Superset 5 baseline so we can use upstream capabilities (including MCP). This includes:

- Moving the codebase and dependencies onto Superset 5
- Upgrading the Superset metadata database
- Rebuilding and validating images / local and deployed environments
- Handling upstream breaking changes that affect how Superset runs

**Why it matters:** everything else in this doc assumes we are actually running Superset 5.

---

## 2. Enable and productize Superset MCP — **L**

Superset 5 includes a built-in MCP service so AI tools can work with dashboards and data. Turning that into a usable product capability means:

- Deciding how users/agents authenticate into MCP in our product
- Deploying and securing the new MCP service in our environments
- Making sure each AI action runs as the right user (permissions and data access still apply)
- Connecting our product / AI clients to that service
- Adjusting or retiring the temporary MCP-related bridge we have in the Portal today
- Basic monitoring so we can see usage and failures

**Why it matters:** this is the main product reason to move to Superset 5; without this work MCP is not a product feature, only an unused upstream capability.

---

## 3. Keep login and Portal↔Superset trust working — **L**

Users sign in via Google / Microsoft / Auth0 and the Portal talks to Superset on their behalf. After the upgrade we must re-validate that login, session continuity, and Portal→Superset access still work end to end.

---

## 4. Roles, permissions, and embedded “guest” access — **M–L**

We use custom roles (including Guest for embedded dashboards). These must be re-checked on Superset 5 so viewers still see only what they should.

---

## 5. Embedded dashboards in the Portal — **M**

Dashboards shown inside the Portal must keep loading correctly for normal (non-admin) users, including refresh of temporary access.

---

## 6. Portal features that call Superset APIs — **M**

Portal screens that list dashboards, manage users/roles, show thumbnails, etc. depend on Superset APIs. Those integrations need a regression pass and likely small fixes where responses or behavior changed.

---

## 7. Our custom Superset changes (fork features) — **L** (depends on scope)

Beyond stock Superset we carry custom behavior (notably saved filter sets, UI tweaks, caching, BigQuery-related patches). For each: **re-apply on 5**, **replace with a simpler approach**, or **drop**. Filter sets are the largest open product decision.

---

## 8. Environments, images, and cutover plumbing — **M**

New images, env vars, deploy topology (including MCP), secrets, and a safe staging→prod path with rollback.

---

## 9. Security configuration for embed, SSO, and MCP — **M**

Confirm that login, embedded dashboards, and the new MCP access model are configured correctly for Superset 5 (including how AI clients authenticate and which users/permissions apply). Validate in staging before production.

This is a **configuration + validation** step aligned with the upgrade, not a separate security project.

---

## 10. Product acceptance testing — **M**

End-to-end checks: login, roles, catalog, embed, user admin, MCP success and denial paths, and any retained custom features.

---

## 11. Docs and client communication — **S–M**

Update internal runbooks and tell stakeholders what changes for them (e.g. if a custom feature is dropped or MCP access rules).

---

## Suggested order (high level)

1. Migrate fork to Superset 5  
2. Restore login / roles / embed basics  
3. Portal catalog & admin regressions  
4. MCP as a product capability  
5. Decide fate of heavy custom fork features  
6. Embed / SSO / MCP config validation + prod cutover + acceptance
