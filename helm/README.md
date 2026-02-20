# Kure Helm Chart

Kubernetes failure diagnosis tool with AI-powered troubleshooting. Detects pod failures (CrashLoopBackOff, ImagePullBackOff, Pending, etc.) instantly and provides contextual solutions to help you fix issues fast.

## Quick Start

```bash
# Add the Helm repository
helm repo add kure-monitor https://nan0c0de.github.io/kure-monitor/
helm repo update

# Install Kure Monitor
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace
```

After installation, access the dashboard and configure your LLM provider via the Admin panel.

## Features

- **Instant Failure Detection** — Detects pod failures across all namespaces in real-time
- **AI-Powered Troubleshooting** — Generates contextual solutions using OpenAI, Anthropic, Groq, or Google Gemini
- **Security Scanning** — Identifies security misconfigurations with remediation guidance
- **Live Pod Logs** — Stream logs on-demand for troubleshooting
- **Cluster Overview** — CPU, memory, and storage usage at a glance
- **Slack Notifications** — Get alerted when failures occur
- **Admin Panel** — Configure AI provider, notifications, and exclusions via UI

## Configuration

### Core Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `agent.clusterMetrics.enabled` | Enable cluster metrics collection | `true` |
| `agent.image.tag` | Agent image tag | `1.6.0` |
| `securityScanner.image.tag` | Security scanner image tag | `1.6.0` |
| `backend.replicaCount` | Backend replica count | `1` |
| `backend.image.tag` | Backend image tag | `1.6.0` |
| `frontend.image.tag` | Frontend image tag | `1.6.0` |

### LLM Configuration

LLM provider is configured via the Admin panel in the web dashboard after installation. No API key is required during helm install.

Supported providers:
- **OpenAI** - `gpt-4.1-mini` (default)
- **Anthropic** - `claude-sonnet-4-20250514` (default)
- **Groq** - `meta-llama/llama-4-scout-17b-16e-instruct` (default)
- **Google Gemini** - `gemini-2.0-flash` (default)

### Service Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `backend.service.type` | Backend service type | `ClusterIP` |
| `backend.service.port` | Backend service port | `8000` |
| `frontend.service.type` | Frontend service type | `ClusterIP` |
| `frontend.service.port` | Frontend service port | `8080` |

### Database Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `postgresql.external` | Use external PostgreSQL | `false` |
| `postgresql.host` | PostgreSQL host (external only) | `""` |
| `postgresql.port` | PostgreSQL port | `5432` |
| `postgresql.database` | Database name | `kure` |
| `postgresql.username` | Database username | `kure` |
| `postgresql.password` | Database password | `kure-password-change-me` |
| `postgresql.persistence.enabled` | Enable persistence | `true` |
| `postgresql.persistence.size` | Storage size | `10Gi` |

### Ingress Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `""` |
| `ingress.hosts[0].host` | Ingress hostname | `kure.local` |

### Security Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `securityContext.runAsNonRoot` | Run as non-root | `true` |
| `securityContext.runAsUser` | User ID | `1001` |
| `securityContext.allowPrivilegeEscalation` | Allow privilege escalation | `false` |
| `securityContext.readOnlyRootFilesystem` | Read-only root filesystem | `true` |

## Components

| Component | Description |
|-----------|-------------|
| **Agent** | DaemonSet that monitors pods and collects cluster metrics |
| **Security Scanner** | Scans pods for security misconfigurations |
| **Backend** | FastAPI server with solution engine and WebSocket support |
| **Frontend** | React dashboard for cluster health visualization |
| **PostgreSQL** | Database for persistent storage |

## Access the Dashboard

```bash
# Via port-forward
kubectl port-forward svc/kure-monitor-frontend 8080:8080 -n kure-system
```

Then open http://localhost:8080 and configure your LLM provider in the Admin panel.

## Requirements

- Kubernetes 1.20+
- Helm 3.0+
- (Optional) metrics-server for CPU/memory metrics

## Upgrade

```bash
helm repo update
helm upgrade kure-monitor kure-monitor/kure --version 1.6.0 -n kure-system
```

## Uninstall

```bash
helm uninstall kure-monitor -n kure-system
```

## License

Licensed under the [Apache License 2.0](https://github.com/Nan0C0de/kure-monitor/blob/main/LICENSE).

"Kure Monitor" is a trademark of Igor Koricanac.
