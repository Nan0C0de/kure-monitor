---
title: Authentication
description: How dashboard user accounts and the service token work in Kure Monitor 2.3+.
---

Kure Monitor 2.3+ uses two separate auth mechanisms:

- **User accounts** for dashboard traffic (`read` / `write` / `admin` roles).
- A **shared service token** for agent and security-scanner traffic.

Both are wired up automatically by the Helm chart — there is nothing to configure at install time. The legacy `AUTH_API_KEY` / `auth.apiKey` single-key model was **removed in 2.3.0**. See the [2.2 → 2.3 migration guide](/kure-monitor/migration/2-2-to-2-3/) for the upgrade path.

## Dashboard (user accounts)

On first visit, the dashboard prompts the very first user to create the initial **admin** account (username + password). Once signed in, invite further users from **Admin Panel → Users** and assign a role:

| Role  | Permissions |
|-------|-------------|
| `read`  | View pod failures and security findings. No mutating actions. |
| `write` | Everything `read` can do, plus dismiss/resolve pods, trigger rescans, edit suppressions. |
| `admin` | Everything `write` can do, plus user management, LLM config, notification settings. |

Sessions are carried in an HttpOnly cookie called `kure_session`, signed with `SESSION_SECRET`. Login is rate-limited (5 attempts per 30 seconds).

## Service-to-service (agent + security scanner)

Agent and scanner authenticate to the backend with a shared `SERVICE_TOKEN`:

- Sent as the `X-Service-Token` HTTP header.
- Sent as `?token=<value>` on WebSocket connections.

## Bootstrap Secret

The Helm chart creates a Secret named `<release>-bootstrap` on first install with two randomly generated keys (`randAlphaNum 48`):

- `service-token` — mounted as `SERVICE_TOKEN` in backend, agent, scanner.
- `session-secret` — mounted as `SESSION_SECRET` in the backend.

On `helm upgrade`, the chart uses `lookup` to read the existing values back, so tokens are preserved and active sessions stay valid.

## Rotating tokens

```bash
# Edit the Secret in place
kubectl edit secret kure-monitor-bootstrap -n kure-system

# Restart the pods that read it
kubectl rollout restart \
  deployment/kure-monitor-backend \
  deployment/kure-monitor-security-scanner \
  -n kure-system
kubectl rollout restart daemonset/kure-monitor-agent -n kure-system
```

Rotating `session-secret` invalidates all existing dashboard sessions and forces every user to log in again.

## Exempt endpoints

These endpoints do **not** require user authentication:

**Ingest (require `X-Service-Token`):**

| Endpoint | Purpose |
|----------|---------|
| `POST /api/pods/failed` | Agent reports pod failures |
| `POST /api/pods/dismiss-deleted` | Agent dismisses deleted pods |
| `POST /api/security/findings` | Scanner reports findings |
| `POST /api/security/scan/clear` | Scanner clears findings |
| `POST /api/security/rescan-status` | Scanner reports rescan status |
| `DELETE /api/security/findings/resource/*` | Scanner deletes resource findings |
| `POST /api/metrics/security-scan-duration` | Scanner reports scan duration |

**Always public:**

| Endpoint | Purpose |
|----------|---------|
| `/health`, `/metrics` | Liveness / Prometheus scrape |
| `GET /api/auth/status` | Check whether initial admin setup is needed |
| `POST /api/auth/login` | Log in with username + password |
| `POST /api/auth/signup` | Create the initial admin (one-shot, only usable when no users exist) |

## Encryption at rest

LLM API keys configured via the Admin panel are encrypted before storage using a Fernet key (`security.encryptionKey` in Helm values). If left empty, the chart auto-generates one.
