# Superset Agent Runbook

## Goal

Operational checklist for agents working in this Superset repository.

## Standard Workflow

1. Install dependencies
   - Python deps per project instructions
   - Frontend deps where needed
2. Start local runtime (preferred for day-to-day)
   - Docker Compose or local dev stack
3. Apply metadata DB migrations before testing changes
4. Run focused tests/lint for touched areas
5. Validate upgrade compatibility when config/DB changes are involved

## Common Commands

- **Dev/bootstrap**
  - `docker compose up -d`
  - `docker compose logs -f`
- **Tests**
  - `pytest`
  - Frontend tests for touched plugins/packages
- **Lint/quality**
  - Python lint/type checks as configured
  - Frontend lint/type checks as configured

## Upgrade-Safe Change Checklist

- If touching configuration defaults, verify against `UPDATING.md`.
- If touching feature flags, update docs and ensure defaults are explicit.
- If touching API behavior, identify permission impact and migration notes.
- If touching metadata models/migrations, assess potential downtime impact.

## Safety Notes

- Do not assume Docker Compose setup is production-ready.
- Never bypass metadata backup strategy before migration in real environments.
- Keep changes minimal and scope tests to impacted layers.
