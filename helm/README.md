# Kure Helm Chart

Kubernetes failure diagnosis tool with AI-powered troubleshooting and security scanning. Detects pod failures (CrashLoopBackOff, ImagePullBackOff, Pending, OOMKilled) instantly and provides contextual solutions to help you fix issues fast.

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

After installation, the dashboard will prompt you to create the initial admin account on first visit, and you can configure your LLM provider via the Admin panel.

## Production Install

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)"
```

The chart auto-generates a Secret named `<release>-bootstrap` on first install
containing a `service-token` (used by the agent and security scanner to
authenticate to the backend) and a `session-secret` (used to sign dashboard
session cookies). Both values are read back on `helm upgrade` via `lookup`, so
upgrades preserve the existing tokens and don't invalidate sessions.

If you scale the backend to multiple replicas, the shared `session-secret`
ensures users stay signed in regardless of which pod handles the request.

## Features

- **Instant Failure Detection** -- Detects pod failures across all namespaces in real-time
- **AI-Powered Troubleshooting** -- Generates contextual solutions using OpenAI, Anthropic, Groq, Google Gemini, or Ollama
- **Security Scanning** -- 50+ checks for security misconfigurations with AI-generated remediation
- **Dashboard Authentication** -- User accounts (read/write/admin) with rate-limited login and HttpOnly session cookies
- **Live Pod Logs** -- Stream logs on-demand for troubleshooting
- **Cluster Overview** -- CPU, memory, and storage usage at a glance
- **Slack & Teams Notifications** -- Get alerted when failures occur
- **Manual Security Rescan** -- Trigger full re-scans on demand
- **Admin Panel** -- Configure AI provider, notifications, exclusions, and trusted registries via UI

## Configuration

### Authentication

The chart manages auth automatically -- there are no `auth.*` values to set at install time.

| Parameter | Description | Default |
|-----------|-------------|---------|
| `security.encryptionKey` | Fernet key for API key encryption. Auto-generated if empty. | `""` |

How it works:

- A Secret named `{{ release }}-bootstrap` is created on first install with two
  keys: `service-token` and `session-secret`. Both are randomly generated
  (`randAlphaNum 48`).
- On `helm upgrade`, the chart uses `lookup` to read the existing values back so
  the tokens are preserved -- service traffic keeps working and active dashboard
  sessions stay valid.
- The backend, agent, and security-scanner pods all consume `SERVICE_TOKEN`
  from this Secret; the backend additionally consumes `SESSION_SECRET`.
- Dashboard users are created in-app: the first visitor is prompted to create
  the initial admin account, and the admin invites further users (read / write
  / admin roles).
- Login attempts are rate-limited (5 attempts per 30 seconds).

To rotate either token, edit the bootstrap Secret and restart the affected
pods (backend + agent + security-scanner for the service token; backend only
for the session secret -- note that rotating the session secret signs all
existing users out).

### Core Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `agent.pendingGracePeriod` | Seconds before reporting Pending pods as failed | `120` |
| `agent.image.tag` | Agent image tag | `2.2.0` |
| `securityScanner.image.tag` | Security scanner image tag | `2.2.0` |
| `backend.replicaCount` | Backend replica count | `1` |
| `backend.image.tag` | Backend image tag | `2.2.0` |
| `frontend.image.tag` | Frontend image tag | `2.2.0` |

### LLM Configuration

LLM provider is configured via the Admin panel in the web dashboard after installation. No API key is required during `helm install` -- configure it when you're ready.

Supported providers:

| Provider | Default Model | Notes |
|----------|---------------|-------|
| **Ollama** | `llama3.2` | Local inference, no API key needed. Set the Ollama URL in Admin panel. |
| **OpenAI** | `gpt-4.1-mini` | Requires OpenAI API key |
| **Anthropic** | `claude-sonnet-4-20250514` | Requires Anthropic API key |
| **Groq** | `llama-4-scout-17b-16e-instruct` | Requires Groq API key |
| **Google Gemini** | `gemini-2.0-flash` | Requires Google AI API key |

If no LLM is configured, Kure uses built-in rule-based solutions as a fallback.

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
| `postgresql.persistence.storageClass` | Storage class (empty for default) | `""` |

### Ingress Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `""` |
| `ingress.hosts[0].host` | Ingress hostname | `kure.local` |
| `ingress.tls` | TLS configuration | `[]` |

Example with NGINX ingress and TLS:

```yaml
ingress:
  enabled: true
  className: nginx
  hosts:
    - host: kure.example.com
      paths:
        - path: /
          pathType: Prefix
          service: frontend
        - path: /api
          pathType: Prefix
          service: backend
  tls:
    - secretName: kure-tls
      hosts:
        - kure.example.com
```

### Prometheus Metrics

| Parameter | Description | Default |
|-----------|-------------|---------|
| `prometheus.enabled` | Enable Prometheus scraping network policy | `false` |
| `prometheus.namespace` | Namespace where Prometheus is deployed | `monitoring` |
| `prometheus.serviceMonitor.enabled` | Create ServiceMonitor resource (requires Prometheus Operator) | `false` |

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
| **Agent** | DaemonSet that monitors pods for failures |
| **Security Scanner** | Scans pods for security misconfigurations (50+ checks) |
| **Backend** | FastAPI server with solution engine, LLM integration, and WebSocket support |
| **Frontend** | React dashboard for cluster health visualization |
| **PostgreSQL** | Database for persistent storage of failures, findings, and configuration |

## Access the Dashboard

```bash
# Via port-forward
kubectl port-forward svc/kure-monitor-frontend 8080:8080 -n kure-system
```

Then open http://localhost:8080. On first visit you'll be prompted to create the initial admin account.

## Examples

### Minimal install

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system --create-namespace
```

The dashboard will prompt you to create the initial admin account on first visit.

### Production install (custom DB password)

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)"
```

### With Prometheus monitoring

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system --create-namespace \
  --set prometheus.enabled=true \
  --set prometheus.serviceMonitor.enabled=true
```

### With ingress

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system --create-namespace \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set "ingress.hosts[0].host=kure.example.com"
```

### With external PostgreSQL

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system --create-namespace \
  --set postgresql.external=true \
  --set postgresql.host=my-postgres.example.com \
  --set postgresql.password=my-secure-password
```

## Requirements

- Kubernetes 1.20+
- Helm 3.0+

## Upgrade

```bash
helm repo update
helm upgrade kure-monitor kure-monitor/kure --version 2.2.0 -n kure-system
```

## Uninstall

```bash
helm uninstall kure-monitor -n kure-system
```

## License

Licensed under the [Apache License 2.0](https://github.com/Nan0C0de/kure-monitor/blob/main/LICENSE).

"Kure Monitor" is a trademark of Igor Koricanac.
