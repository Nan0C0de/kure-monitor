---
title: API Reference
description: Complete REST API reference for the Kure Monitor backend — pods, security, mirror, diagram, admin, WebSocket.
---

Complete REST API documentation for the Kure Monitor backend.

**Base URL:** `http://<backend-host>:8000/api`

## Authentication

Two distinct mechanisms (since 2.3.0):

- **User sessions** (cookie-based) for dashboard / browser traffic
- **Service token** (`X-Service-Token` header) for agent and scanner traffic

The legacy `AUTH_API_KEY` / `auth.apiKey` single-key model was removed in 2.3.0.

### User sessions (dashboard)

Log in with `POST /api/auth/login` (username + password). On success the backend sets an HttpOnly cookie named `kure_session`, signed with `SESSION_SECRET`. All subsequent `/api/*` calls from the browser use that cookie automatically.

Rate limit: **5 login attempts per 30 seconds**.

### Service token (agent / scanner)

Ingest endpoints authenticate with the `X-Service-Token` HTTP header:

```
X-Service-Token: <SERVICE_TOKEN value>
```

WebSocket and SSE log streams use a query parameter instead:

```
ws://localhost:8000/api/ws?token=YOUR_SERVICE_TOKEN
GET /api/pods/{namespace}/{pod_name}/logs/stream?token=YOUR_SERVICE_TOKEN
```

### Always-public endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health`, `GET /metrics` | Liveness / Prometheus scrape |
| `GET /api/auth/status` | Whether initial admin setup is needed |
| `POST /api/auth/login` | Log in with username + password |
| `POST /api/auth/signup` | Create the initial admin (only when no users exist) |
| `POST /api/chatops/slack/*` | External webhook for Slack interactivity |
| `POST /api/chatops/teams/*` | External webhook for Teams interactivity |

### Service-token-only ingest

| Endpoint | Caller |
|----------|--------|
| `POST /api/pods/failed` | Agent |
| `POST /api/pods/dismiss-deleted` | Agent |
| `POST /api/security/findings` | Scanner |
| `POST /api/security/scan/clear` | Scanner |
| `POST /api/security/rescan-status` | Scanner |
| `DELETE /api/security/findings/resource/{type}/{ns}/{name}` | Scanner |
| `POST /api/metrics/security-scan-duration` | Scanner |

### Error response

```http
401 Unauthorized
{
  "detail": "Not authenticated"
}
```

## Endpoints overview

| Category | Endpoint | Description |
|----------|----------|-------------|
| Config | `GET /config` | App status |
| Pods | `POST /pods/failed` | Report failure |
| Pods | `GET /pods/failed` | List active failures |
| Pods | `GET /pods/history` | List resolved pods |
| Pods | `GET /pods/ignored` | List ignored pods |
| Pods | `PUT /pods/{id}/status` | Update status |
| Pods | `DELETE /pods/failed/{id}` | Dismiss |
| Pods | `POST /pods/failed/{id}/retry-solution` | Regenerate AI solution |
| Pods | `GET /pods/{ns}/{name}/logs` | Get logs |
| Security | `POST /security/findings` | Report finding |
| Security | `GET /security/findings` | List findings |
| Security | `POST /security/findings/{id}/fix` | Generate AI fix |
| Security | `GET / POST / DELETE /security/trusted-registries` | Manage trusted registries |
| Advice | `GET /advice/findings` | List active advice |
| Advice | `POST /advice/findings/{id}/explain` | Lazy AI explanation |
| Advice | `PUT /advice/findings/{id}/ignore` | Suppress finding |
| Advice | `GET /advice/detectors` | List available detectors |
| ChatOps | `POST /chatops/slack/events` | Slack URL Verification & Events |
| ChatOps | `POST /chatops/slack/interact` | Slack Interactive Buttons |
| ChatOps | `POST /chatops/teams/interact` | MS Teams Interactive Buttons |
| Mirror | `POST /mirror/preview/{id}` | Generate fixed manifest |
| Mirror | `POST /mirror/deploy/{id}` | Deploy mirror pod |
| Mirror | `GET /mirror/status/{id}` | Mirror status |
| Mirror | `DELETE /mirror/{id}` | Delete mirror |
| Mirror | `GET /mirror/active` | List active mirrors |
| Diagram | `GET /diagram/namespaces` | List namespaces |
| Diagram | `GET /diagram/namespace/{ns}` | Per-namespace graph |
| Diagram | `GET /diagram/workload/{ns}/{kind}/{name}` | Per-workload graph |
| Diagram | `GET /diagram/manifest/{ns}/{kind}/{name}` | Live manifest (rejects `Secret` with 403) |
| Admin | `GET / POST / DELETE /admin/llm/*` | LLM config |
| Admin | `GET / POST / DELETE /admin/excluded-*` | Suppressions |
| Admin | `GET / POST / PUT / DELETE /admin/notifications` | Notifications |
| Admin | `GET / POST /admin/settings/*` | App settings |

## Pod monitoring

### Report failed pod

```http
POST /api/pods/failed
```

Request body:

```json
{
  "pod_name": "my-app-7d9f8b6c4-abc12",
  "namespace": "default",
  "node_name": "worker-1",
  "failure_reason": "CrashLoopBackOff",
  "failure_message": "Back-off restarting failed container",
  "creation_timestamp": "2024-01-15T10:30:00Z",
  "events": [...],
  "container_statuses": [...],
  "manifest": "apiVersion: v1\nkind: Pod\n...",
  "logs": "Error: Database connection failed..."
}
```

Response `200`:

```json
{
  "id": 1,
  "pod_name": "my-app-7d9f8b6c4-abc12",
  "namespace": "default",
  "failure_reason": "CrashLoopBackOff",
  "solution": "## Root Cause\n...",
  "events": [...],
  "container_statuses": [...],
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### List failed pods

```http
GET /api/pods/failed
```

Returns all active (non-dismissed) failures.

### Get history / ignored

```http
GET /api/pods/history
GET /api/pods/ignored
```

### Update status

```http
PUT /api/pods/{pod_id}/status
{
  "status": "investigating"
}
```

Valid: `new`, `investigating`, `resolved`, `ignored`.

### Dismiss / restore

```http
DELETE /api/pods/failed/{pod_id}
PUT /api/pods/ignored/{pod_id}/restore
```

### Retry AI

```http
POST /api/pods/failed/{pod_id}/retry-solution
```

### Get logs

```http
GET /api/pods/{namespace}/{pod_name}/logs
  ?container=app
  &tail_lines=100
  &previous=false
```

### Stream logs (SSE)

```http
GET /api/pods/{namespace}/{pod_name}/logs/stream
  ?container=app
  &tail_lines=100
  &token=<SERVICE_TOKEN>
```

## Security

### Report finding

```http
POST /api/security/findings
{
  "resource_type": "Pod",
  "resource_name": "my-app-7d9f8b6c4-abc12",
  "namespace": "default",
  "check_name": "privileged_container",
  "severity": "critical",
  "message": "Container 'app' is running in privileged mode",
  "remediation": "Remove 'privileged: true' from securityContext",
  "details": {"container": "app", "field": "securityContext.privileged"}
}
```

### List / dismiss / restore / clear

```http
GET    /api/security/findings
DELETE /api/security/findings/{id}
PUT    /api/security/findings/{id}/restore
POST   /api/security/scan/clear
DELETE /api/security/findings/resource/{type}/{ns}/{name}
```

### Generate AI fix

```http
POST /api/security/findings/{id}/fix
```

Returns the LLM-generated remediation.

### Trusted registries

```http
GET    /api/security/trusted-registries
POST   /api/security/trusted-registries  { "registry": "..." }
DELETE /api/security/trusted-registries/{registry}
```

## Mirror Pod Testing

### Preview fix

```http
POST /api/mirror/preview/{pod_id}
```

Returns:

```json
{
  "fixed_manifest": "apiVersion: v1\nkind: Pod\n...",
  "explanation": "## Changes Made\n1. Added resource limits...",
  "is_fallback": false
}
```

### Deploy

```http
POST /api/mirror/deploy/{pod_id}
{
  "ttl_seconds": 180,
  "manifest": "apiVersion: v1\nkind: Pod\n..."   // optional, overrides preview
}
```

Returns:

```json
{
  "mirror_id": "abc123",
  "mirror_pod_name": "my-app-mirror-abc123",
  "namespace": "default",
  "status": "Pending",
  "ttl_seconds": 180,
  "created_at": "2026-03-26T10:30:00Z",
  "fixed_manifest": "...",
  "explanation": "..."
}
```

### Status / delete / list

```http
GET    /api/mirror/status/{mirror_id}
DELETE /api/mirror/{mirror_id}
GET    /api/mirror/active
```

### TTL setting

```http
GET /api/admin/settings/mirror-ttl
PUT /api/admin/settings/mirror-ttl  { "seconds": 300 }
```

Range: 30 – 3600 seconds. Admin role required for `PUT`.

## Diagram

> Introduced in **2.3.2**. All endpoints gated by `require_read`.

### List namespaces

```http
GET /api/diagram/namespaces
```

```json
{ "namespaces": ["default", "kube-system", "kure-system"] }
```

### Per-namespace graph

```http
GET /api/diagram/namespace/{namespace}
```

```json
{
  "nodes": [{ "id": "...", "kind": "Deployment", "name": "...", "namespace": "..." }],
  "edges": [{ "id": "...", "source": "...", "target": "...", "kind": "owns" }],
  "groups": [{ "id": "...", "label": "my-app", "members": ["..."] }]
}
```

### Per-workload graph

```http
GET /api/diagram/workload/{namespace}/{kind}/{name}
```

Valid `kind` values: `Deployment`, `StatefulSet`, `DaemonSet`, `Job`, `CronJob`. Same response shape as the namespace graph.

### Get node manifest

```http
GET /api/diagram/manifest/{namespace}/{kind}/{name}
```

Returns the live manifest as YAML. **Rejects `kind=Secret` with HTTP 403** by design — the backend ServiceAccount has no read access to Secrets. Synthesized kinds (`Permission`, `Subject:User`, `Subject:Group`) are rejected with HTTP 400 because they have no underlying manifest.

### List Roles + ClusterRoles

> Added in **2.3.3**.

```http
GET /api/diagram/roles
```

```json
{
  "cluster_roles": [{ "name": "..." }],
  "roles": [{ "namespace": "...", "name": "..." }]
}
```

### Per-Role graph

> Added in **2.3.3**.

```http
GET /api/diagram/role/{namespace}/{name}
```

Same response shape as the namespace graph. Nodes include the `Role`, its `RoleBinding`s, synthesized `Permission` nodes (one per `(apiGroup, resource)` tuple, with verbs and `resourceNames` in `metadata`), and `Subject:User` / `Subject:Group` / `Subject:ServiceAccount` nodes.

### Per-ClusterRole graph

> Added in **2.3.3**.

```http
GET /api/diagram/clusterrole/{name}
```

Same shape as the per-Role graph but for ClusterRoles + ClusterRoleBindings.

## Admin — LLM

```http
GET    /api/admin/llm/status
POST   /api/admin/llm/config   { "provider": "...", "api_key": "...", "model": "..." }
POST   /api/admin/llm/test     { "provider": "...", "api_key": "...", "model": "..." }
DELETE /api/admin/llm/config
```

See [LLM Providers](/configuration/llm-providers/) for supported provider/model combinations.

## Admin — Exclusions

```http
GET    /api/admin/excluded-namespaces
POST   /api/admin/excluded-namespaces   { "namespace": "kube-system" }
DELETE /api/admin/excluded-namespaces/{namespace}

GET    /api/admin/excluded-pods
POST   /api/admin/excluded-pods         { "pod_name": "test-*" }
DELETE /api/admin/excluded-pods/{pod_name}
```

## Admin — Notifications

```http
GET    /api/admin/notifications
POST   /api/admin/notifications
PUT    /api/admin/notifications/{provider}
DELETE /api/admin/notifications/{provider}
POST   /api/admin/notifications/{provider}/test
```

Sample body:

```json
{
  "provider": "slack",
  "enabled": true,
  "config": { "webhook_url": "https://hooks.slack.com/services/..." }
}
```

## Admin — Settings

```http
GET  /api/admin/settings/{key}
POST /api/admin/settings/{key}    { "value": "10080" }
```

Common keys:

- `history_retention_minutes` — auto-delete resolved pods after N minutes (`0` = disabled)
- `ignored_retention_minutes` — auto-delete ignored pods after N minutes (`0` = disabled)

## WebSocket

```
WS /api/ws
```

Push messages from the backend:

```json
{ "type": "pod_failure", "data": { "id": 1, "pod_name": "...", "solution": "..." } }
{ "type": "pod_deleted", "data": { "namespace": "default", "pod_name": "..." } }
{ "type": "solution_updated", "data": { "id": 1, "solution": "..." } }
{ "type": "security_finding", "data": { "id": 1, "severity": "critical", "message": "..." } }
{ "type": "namespace_exclusion", "data": { "namespace": "kube-system", "action": "excluded" } }
{ "type": "trusted_registry_change", "data": { "registry": "...", "action": "added" } }
{ "type": "pod_status_change", "data": { "id": 1, "status": "investigating" } }
{ "type": "security_rescan_status", "data": { "status": "started", "reason": "trusted_registry_change" } }
```

## Error responses

| Status | Body |
|--------|------|
| `400` | `{ "detail": "Pod name and namespace are required" }` |
| `401` | `{ "detail": "Not authenticated" }` |
| `403` | `{ "detail": "Secret manifests are not readable by design." }` |
| `404` | `{ "detail": "Pod failure not found" }` |
| `500` | `{ "detail": "Internal server error..." }` |
| `503` | `{ "detail": "Kubernetes client not available" }` |

## OpenAPI / interactive docs

- **Swagger UI**: `http://<backend-host>:8000/docs`
- **ReDoc**: `http://<backend-host>:8000/redoc`
