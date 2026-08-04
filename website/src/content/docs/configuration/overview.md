---
title: Configuration Overview
description: How to configure Kure Monitor — Helm values, in-dashboard admin settings, and environment variables.
---

Kure Monitor is configured in three layers:

| Layer | What it controls | Set via |
|-------|------------------|---------|
| **Helm chart** | Resource limits, replicas, image tags, ingress, PostgreSQL, Prometheus, NetworkPolicies | `values.yaml` or `--set` |
| **Admin panel (in dashboard)** | LLM provider, notifications, exclusions, trusted registries, retention, mirror pod TTL | The **Admin** tab in the UI |
| **Bootstrap Secret** | `SERVICE_TOKEN` and `SESSION_SECRET` for auth | Auto-created by the chart on first install |

Anything that changes between environments (db password, ingress host, replicas) belongs in Helm values. Anything that changes per-team or per-week (which LLM, which namespaces to exclude, where to send Slack alerts) belongs in the Admin panel — those settings persist in PostgreSQL and survive upgrades.

## The bootstrap Secret

On first `helm install`, the chart creates a Secret named `<release>-bootstrap` containing two randomly generated keys:

- `service-token` — mounted as `SERVICE_TOKEN` in backend, agent, and scanner. Authenticates agent/scanner traffic to the backend.
- `session-secret` — mounted as `SESSION_SECRET` in the backend. Signs dashboard session cookies.

On `helm upgrade`, the chart uses `lookup` to read the existing values back, so tokens are preserved and active sessions stay valid across upgrades.

If you scale the backend beyond one replica, having a stable `session-secret` across replicas is important — the chart handles this for you.

## Custom values file

Create a `values.yaml` for your environment:

```yaml
agent:
  enabled: true

securityScanner:
  enabled: true

backend:
  replicaCount: 2
  resources:
    requests:
      cpu: 500m
      memory: 512Mi

frontend:
  service:
    type: LoadBalancer

postgresql:
  password: "your-secure-password"
  persistence:
    size: 50Gi
    storageClass: fast-ssd

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: kure.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: kure-tls
      hosts:
        - kure.example.com
```

Install with:

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system --create-namespace \
  -f values.yaml
```

## Environment variables

### Backend

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (auto-generated) |
| `SERVICE_TOKEN` | Shared token for agent/scanner → backend traffic (mounted from `<release>-bootstrap`) |
| `SESSION_SECRET` | Signing key for dashboard session cookies (mounted from `<release>-bootstrap`) |
| `PYTHONUNBUFFERED` | Python output buffering (set to `"1"`) |

### Agent

| Variable | Description |
|----------|-------------|
| `KURE_CHECK_INTERVAL` | Pod check interval in seconds |
| `KURE_LOG_LEVEL` | Logging level (`INFO`, `DEBUG`, `WARNING`) |

## What to read next

- [Helm Values](/configuration/helm-values/) — full parameter reference
- [LLM Providers](/configuration/llm-providers/) — supported providers, models, and recommended picks
- [Authentication](/configuration/authentication/) — user accounts and the service token in detail
