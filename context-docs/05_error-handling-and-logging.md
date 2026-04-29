# Superset Error Handling and Logging

## Introduction

Superset should handle errors with clear boundaries:

- Normalize exceptions at API/service boundaries.
- Surface safe, actionable messages to clients.
- Preserve rich diagnostics in server logs.
- Avoid leaking credentials, SQL secrets, or internal topology.

## Layered Error Flow

![Superset error flow](./img/error-handling-flow.svg)

## Error Handling Rules

- Convert driver/HTTP/IO exceptions into consistent application-level exceptions.
- Keep HTTP status mapping deterministic (4xx for client/authz/validation, 5xx for server/dependency failures).
- Include correlation/request identifiers in logs and responses where available.
- Prefer fail-closed behavior for security-sensitive paths (auth, permissions, SQL execution controls).

## Logging Rules

- Use structured logs with operation name, actor, object IDs, latency, and outcome.
- Log at `INFO` for normal lifecycle events and `ERROR` for failed operations.
- Use `DEBUG` for deep traces in development only.
- Redact tokens, secrets, connection URIs, and sensitive query parameters.

## Operational Checks

- Verify log verbosity defaults during upgrades (for example DEBUG to INFO shifts).
- Ensure async worker failures (alerts/reports/query tasks) are observable in centralized logs/metrics.
- Track spikes in permission-denied and database-connection errors after releases.
