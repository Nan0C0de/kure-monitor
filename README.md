# Kure Monitor

[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/kure-monitor)](https://artifacthub.io/packages/search?repo=kure-monitor)

> **Stop debugging Kubernetes failures manually — let AI analyze your pod crashes, image pull errors, and scheduling issues in seconds.**

Kure is a Kubernetes health monitoring tool that helps you understand **why** your workloads fail. When a pod crashes, gets stuck pending, or can't pull an image, Kure detects it instantly and provides AI-generated troubleshooting guidance to help you fix it fast. It also continuously scans your cluster for security misconfigurations and gives you a real-time overview of cluster resources — all from a single dashboard.

[Few Screenshots](docs/images)

## Why Kure?

Unlike tools such as K8sGPT that are CLI-focused, Kure gives you a unified web dashboard combining real-time failure diagnosis, security scanning, and AI-powered fixes in one place. It also supports Ollama for fully local, air-gapped LLM inference — so your cluster data never leaves your network.

## Features

**Core Diagnosis**
- **AI-Powered Troubleshooting** — Get contextual solutions generated from pod events, logs, and manifest analysis using OpenAI, Anthropic, Groq, Google Gemini, or Ollama
- **Real-time Failure Detection** — Know immediately when pods enter CrashLoopBackOff, ImagePullBackOff, Pending, OOMKilled, or other failure states
- **Security Scanning** — 50+ checks including privileged containers, host namespace access, dangerous capabilities, missing seccomp/AppArmor profiles, root containers, RBAC misconfigurations, untrusted image registries, and missing resource limits
- **Pod Lifecycle Management** — Track pods through investigating, resolved, and ignored states with configurable history retention

**Dashboard**
- **Live Pod Logs** — Stream logs in real-time with container selection
- **Cluster Overview** — CPU, memory, and storage usage at a glance
- **Export Findings** — Export security findings to CSV, JSON, and PDF
- **Slack & Teams Notifications** — Get alerted when failures occur
- **Dashboard Authentication** — Optional API key auth with login page and rate limiting
- **Prometheus Metrics** — `/metrics` endpoint with optional ServiceMonitor support

## Limitations

Kure is focused on failure diagnosis, not general observability:

- **No Prometheus dependency** — Kure works standalone; it doesn't require or replace Prometheus
- **Not a metrics platform** — No time-series data, no alerting rules, no historical dashboards
- **Not a log aggregator** — Logs are fetched on-demand, not stored or indexed
- **Single cluster only** — Monitors one Kubernetes cluster per installation

Kure complements your existing observability stack (Prometheus, Grafana, Datadog) — it doesn't replace it.

## What's New in v2.0.0

- **Dashboard Authentication** - Optional API key auth with login page to protect your dashboard
- **WebSocket Security** - All real-time connections now require valid authentication when auth is enabled
- **Login Rate Limiting** - Brute-force protection with 5 attempts per 30-second cooldown
- **Security Rescan Button** - Trigger a full security re-scan on demand from the dashboard
- **Ollama Support** - Run fully local LLM inference for air-gapped deployments
- **Teams Notifications** - Microsoft Teams webhook support alongside Slack
- **Auth Warning Banner** - Admin panel warns when authentication is not configured

## Architecture

```
                         Kubernetes Cluster
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │   ┌──────────────┐     ┌──────────────────┐     ┌───────────┐ │
  │   │    Agent     │────>│                  │<────│ Frontend  │ │
  │   │ (DaemonSet)  │ HTTP│     Backend      │ WS  │  (React)  │ │
  │   └──────┬───────┘     │    (FastAPI)     │     └───────────┘ │
  │          │             │                  │                    │
  │   ┌──────┴───────┐    │                  │                    │
  │   │   Security   │───>│                  │                    │
  │   │   Scanner    │HTTP└────────┬─────────┘                    │
  │   └──────┬───────┘             │                              │
  │          │                     │                              │
  │          │              ┌──────┴───────┐                      │
  │    K8s API Server       │  PostgreSQL  │                      │
  │   (watch pods,          │   Database   │                      │
  │    events, nodes)       └──────────────┘                      │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
                                   │
                                   │ API call
                                   ▼
                          ┌──────────────────┐
                          │   LLM Provider   │
                          │ OpenAI/Anthropic │
                          │ Groq/Gemini/     │
                          │ Ollama (local)   │
                          └──────────────────┘
```

**Data flow:**
1. **Agent** and **Security Scanner** watch the Kubernetes API for pod failures and security misconfigurations
2. They report findings to the **Backend** via HTTP
3. **Backend** generates AI solutions using the configured LLM provider (or falls back to rule-based solutions)
4. **Backend** stores results in **PostgreSQL** and pushes real-time updates to the **Frontend** via WebSocket
5. **Frontend** displays the dashboard with live updates

**Components:**

| Component | Type | Description |
|-----------|------|-------------|
| **Agent** | DaemonSet | Watches K8s API for pod failures (CrashLoopBackOff, ImagePullBackOff, Pending, OOMKilled) and collects cluster metrics |
| **Security Scanner** | Deployment | Audits pods for 50+ security misconfigurations with real-time change detection |
| **Backend** | Deployment | FastAPI server — receives reports, generates AI solutions, serves API and WebSocket |
| **Frontend** | Deployment | React dashboard with real-time updates via WebSocket |
| **PostgreSQL** | Deployment | Stores failure history, security findings, and configuration |

## Quick Start

### Prerequisites
- Kubernetes cluster (1.20+)
- kubectl configured
- Helm 3.x (recommended)

### Deploy with Helm (Recommended)

```bash
# Add the Helm repository
helm repo add kure-monitor https://nan0c0de.github.io/kure-monitor/
helm repo update

# Install Kure Monitor
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace
```

After installation, configure your LLM provider (OpenAI, Anthropic, Groq, Google Gemini, or Ollama) via the Admin panel in the web dashboard to enable AI-powered solutions.

### Production Install (with Authentication)

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set auth.apiKey="$(openssl rand -base64 32)" \
  --set postgresql.password="$(openssl rand -base64 24)"
```

### Access the Dashboard

```bash
# Via port-forward (recommended for testing)
kubectl port-forward svc/kure-monitor-frontend 8080:8080 -n kure-system
# Open http://localhost:8080

# OR via NodePort
kubectl get svc -n kure-system
# Access via http://<node-ip>:<nodePort>
```

## Configuration

### LLM Configuration (Admin Panel)

LLM provider is configured via the Admin panel in the web dashboard after installation. No API key is required during helm install.

### Supported LLM Providers

| Provider | Default Model | Alternative Models |
|----------|---------------|--------------------|
| **Ollama** (local) | `llama3.2` | Any model available in your Ollama instance |
| **OpenAI** | `gpt-4.1-mini` | `gpt-4.1`, `gpt-4o` |
| **Anthropic** | `claude-sonnet-4-20250514` | `claude-opus-4-5-20251124`, `claude-haiku-4-5-20251015` |
| **Groq** | `meta-llama/llama-4-scout-17b-16e-instruct` | `meta-llama/llama-4-maverick-17b-128e-instruct`, `llama-3.3-70b-versatile` |
| **Google Gemini** | `gemini-2.0-flash` | `gemini-2.5-pro-preview-05-06`, `gemini-2.0-flash-lite` |

**Provider Aliases:** `claude` -> `anthropic`, `groq_cloud` -> `groq`, `google` -> `gemini`

### Key Helm Values

```yaml
agent:
  pendingGracePeriod: 120   # Seconds before reporting Pending pods
  clusterMetrics:
    enabled: true            # Cluster metrics collection

auth:
  apiKey: ""                 # Set to enable dashboard authentication

postgresql:
  external: false            # Set true to use external PostgreSQL
  password: "change-me"      # Change in production

prometheus:
  enabled: false             # Enable Prometheus scraping network policy
  serviceMonitor:
    enabled: false           # Create ServiceMonitor (requires Prometheus Operator)
```

See [`helm/README.md`](helm/README.md) for the full parameter reference.

## Dashboard Features

### Pod Failures Tab
- Real-time pod failure detection
- AI-generated or rule-based solutions
- Expandable details with events, logs, and manifest
- Pod lifecycle states: investigating, resolved, ignored
- Dismiss/restore with configurable history retention
- Retry AI solution generation

### Security Tab
- 50+ security misconfiguration checks
- Severity-based filtering (Critical, High, Medium, Low)
- AI-generated remediation suggestions
- Export findings to CSV, JSON, and PDF
- Manual rescan button for on-demand re-scanning
- Trusted container registries to suppress untrusted registry findings
- Rule exclusions with global and per-namespace scopes

### Cluster Metrics Tab
- Real-time CPU, memory, and storage usage
- Node status and details
- Pod list with logs viewer
- Live log streaming with play/pause
- Namespace filtering

### Admin Panel
- **AI Config** — Configure LLM provider (OpenAI, Anthropic, Groq, Google Gemini, or Ollama)
- **Notifications** — Configure Slack or Microsoft Teams webhooks for alerts
- **Exclusions** — Exclude namespaces, pods, and security rules from monitoring
- **Trusted Registries** — Mark container registries as trusted to filter findings
- **History** — Configure retention for resolved and ignored pods

## Monitoring and Troubleshooting

### Check System Status
```bash
# Pod status
kubectl get pods -n kure-system

# View logs
kubectl logs -l app.kubernetes.io/component=backend -n kure-system
kubectl logs -l app.kubernetes.io/component=agent -n kure-system
kubectl logs -l app.kubernetes.io/component=security-scanner -n kure-system
kubectl logs -l app.kubernetes.io/component=frontend -n kure-system
```

### Metrics Server Installation

For full cluster metrics (CPU/memory usage), install metrics-server:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

## Authentication

Kure Monitor supports optional API key authentication. When enabled, the dashboard requires login and all API requests must include a valid key.

### Enable Authentication

```bash
# Generate a secure API key
openssl rand -base64 32

# Install with auth enabled
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set auth.apiKey=YOUR_GENERATED_KEY
```

When `auth.apiKey` is set:
- The dashboard shows a login page
- All API and WebSocket connections require authentication
- Agent and security scanner authenticate automatically via the same key
- Login attempts are rate-limited (5 per 30 seconds)

When `auth.apiKey` is empty (default), authentication is disabled and the dashboard is open.

## Security

- **Authentication** — Optional API key auth for dashboard, API, and WebSocket access
- **Authenticated internal traffic** — Agent and scanner authenticate to backend with Bearer tokens
- All components run as non-root users (UID 1001)
- Network policies restrict inter-pod communication
- RBAC limits agent and scanner permissions to read-only access
- Security contexts prevent privilege escalation with read-only root filesystem
- Seccomp profiles enabled (RuntimeDefault)

## License

Licensed under the [Apache License 2.0](LICENSE).

"Kure Monitor" is a trademark of Igor Koricanac. See [LICENSE](LICENSE) for trademark details.
