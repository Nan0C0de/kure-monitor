---
title: Helm Values
description: Complete reference for every Helm value supported by the Kure Monitor chart.
---

Reference for every Helm value in the Kure Monitor chart. For canonical defaults see [`helm/values.yaml`](https://github.com/igor-koricanac/kure-monitor/blob/main/helm/values.yaml) and [`helm/README.md`](https://github.com/igor-koricanac/kure-monitor/blob/main/helm/README.md).

## Feature toggles

Each of the four dashboard features can be individually enabled or
disabled. All four default to `true`. Disabling a feature hides its tab
in the dashboard and, where applicable, skips deploying its dedicated
workloads / RBAC / NetworkPolicies.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `features.podMonitoring` | Enable Pod Monitoring. When `false`, the agent DaemonSet and its RBAC are not deployed, and the Monitoring tab is hidden. | `true` |
| `features.securityScan` | Enable Security Scanning. When `false`, the security-scanner Deployment and its RBAC are not deployed, and the Security tab is hidden. | `true` |
| `features.diagram` | Enable the Topology Diagram tab. UI-only toggle — backend APIs remain available; the Diagram tab is hidden when `false`. | `true` |
| `features.aiAdvice` | Enable the AI Advice tab. UI-only toggle — backend `/api/advice/*` routes remain available; the Advice tab is hidden when `false`. | `true` |

Example — only run pod monitoring, skip everything else:

```yaml
features:
  podMonitoring: true
  securityScan: false
  diagram: false
  aiAdvice: false
```

## Agent

The agent runs as a DaemonSet (one pod per node) and watches the Kubernetes API for pod failures. Deployed only when `features.podMonitoring=true`.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `agent.pendingGracePeriod` | Seconds before pending pods are flagged | `120` |
| `agent.image.repository` | Agent image repository | `ghcr.io/igor-koricanac/kure-monitor/agent` |
| `agent.image.tag` | Agent image tag | `2.4.3` |
| `agent.resources.requests.cpu` | CPU request | `100m` |
| `agent.resources.requests.memory` | Memory request | `128Mi` |
| `agent.resources.limits.cpu` | CPU limit | `500m` |
| `agent.resources.limits.memory` | Memory limit | `512Mi` |

## Security Scanner

Deployed only when `features.securityScan=true`.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `securityScanner.image.tag` | Scanner image tag | `2.4.3` |
| `securityScanner.resources.requests.cpu` | CPU request | `100m` |
| `securityScanner.resources.requests.memory` | Memory request | `128Mi` |

## Backend

| Parameter | Description | Default |
|-----------|-------------|---------|
| `backend.replicaCount` | Number of replicas | `1` |
| `backend.image.tag` | Backend image tag | `2.4.3` |
| `backend.service.type` | Service type | `ClusterIP` |
| `backend.service.port` | Service port | `8000` |
| `backend.resources.requests.cpu` | CPU request | `200m` |
| `backend.resources.requests.memory` | Memory request | `256Mi` |
| `backend.resources.limits.cpu` | CPU limit | `1000m` |
| `backend.resources.limits.memory` | Memory limit | `1Gi` |

## Frontend

| Parameter | Description | Default |
|-----------|-------------|---------|
| `frontend.replicaCount` | Number of replicas | `1` |
| `frontend.image.tag` | Frontend image tag | `2.4.3` |
| `frontend.service.type` | Service type | `ClusterIP` |
| `frontend.service.port` | Service port | `8080` |
| `frontend.service.nodePort` | NodePort (if `type=NodePort`) | `""` |

## PostgreSQL

| Parameter | Description | Default |
|-----------|-------------|---------|
| `postgresql.external` | Use external PostgreSQL | `false` |
| `postgresql.host` | PostgreSQL host (external only) | `""` |
| `postgresql.port` | PostgreSQL port | `5432` |
| `postgresql.database` | Database name | `kure` |
| `postgresql.username` | Database username | `kure` |
| `postgresql.password` | Database password | `kure-password-change-me` |
| `postgresql.persistence.enabled` | Enable persistent storage | `true` |
| `postgresql.persistence.size` | Storage size | `10Gi` |
| `postgresql.persistence.storageClass` | Storage class | `""` |

To use an external PostgreSQL:

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system --create-namespace \
  --set postgresql.external=true \
  --set postgresql.host=your-postgres-host.example.com \
  --set postgresql.port=5432 \
  --set postgresql.database=kure \
  --set postgresql.username=kure \
  --set postgresql.password=your-password
```

## Ingress

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class | `""` |
| `ingress.annotations` | Ingress annotations | `{}` |
| `ingress.hosts[0].host` | Hostname | `kure.local` |
| `ingress.tls` | TLS configuration | `[]` |

## Security context

| Parameter | Description | Default |
|-----------|-------------|---------|
| `securityContext.runAsNonRoot` | Run as non-root user | `true` |
| `securityContext.runAsUser` | User ID | `1001` |
| `securityContext.runAsGroup` | Group ID | `1001` |
| `securityContext.allowPrivilegeEscalation` | Allow privilege escalation | `false` |
| `securityContext.readOnlyRootFilesystem` | Read-only root filesystem | `true` |

## Prometheus

| Parameter | Description | Default |
|-----------|-------------|---------|
| `prometheus.enabled` | Enable Prometheus metrics integration | `false` |
| `prometheus.namespace` | Namespace where Prometheus runs | `monitoring` |
| `prometheus.serviceMonitor.enabled` | Create ServiceMonitor (requires Operator) | `false` |

Enable Prometheus integration:

```yaml
prometheus:
  enabled: true
  namespace: monitoring
  serviceMonitor:
    enabled: true
```

## Auth-related values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `security.encryptionKey` | Fernet key for API-key encryption (auto-generated if empty). Unrelated to dashboard auth. | `""` |

There is **no** `auth.apiKey` value in 2.3+. The legacy single-key model was removed — see [the migration guide](/kure-monitor/migration/2-2-to-2-3/) and [Authentication](/kure-monitor/configuration/authentication/).
