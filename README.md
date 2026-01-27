# Kure Monitor

[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/kure-monitor)](https://artifacthub.io/packages/search?repo=kure-monitor)

> **Stop debugging Kubernetes failures manually — let AI analyze your pod crashes, image pull errors, and scheduling issues in seconds.**

Kure is a failure diagnosis tool that helps you understand **why** your Kubernetes workloads fail. When a pod crashes, gets stuck pending, or can't pull an image, Kure detects it instantly and provides AI-generated troubleshooting guidance to help you fix it fast.

[Few Screenshots](docs/images)

## Features

**Core Diagnosis**
- **AI-Powered Troubleshooting** — Get contextual solutions generated from pod events, logs, and manifest analysis using OpenAI, Anthropic, Groq, or Google Gemini
- **Real-time Failure Detection** — Know immediately when pods enter CrashLoopBackOff, ImagePullBackOff, Pending, or other failure states
- **Security Scanning** — 50+ checks including privileged containers, host namespace access, dangerous capabilities, missing seccomp/AppArmor profiles, root containers, RBAC misconfigurations, untrusted image registries, and missing resource limits

**Dashboard**
- **Live Pod Logs** — Stream logs in real-time with container selection
- **Cluster Overview** — CPU, memory, and storage usage at a glance
- **Slack Notifications** — Get alerted when failures occur

## Limitations

Kure is focused on failure diagnosis, not general observability:

- **No Prometheus dependency** — Kure works standalone; it doesn't require or replace Prometheus
- **Not a metrics platform** — No time-series data, no alerting rules, no historical dashboards
- **Not a log aggregator** — Logs are fetched on-demand, not stored or indexed
- **Single cluster only** — Monitors one Kubernetes cluster per installation

Kure complements your existing observability stack (Prometheus, Grafana, Datadog) — it doesn't replace it.

## What's New in v1.5.0

- **Google Gemini Support** - New LLM provider with Gemini 2.5 Pro, 2.0 Flash, and 2.0 Flash Lite models
- **Redesigned Admin Panel** - New tabbed interface for better navigation (AI Config, Notifications, Exclusions)
- **Simplified Exclusions** - Security and Monitoring exclusions merged into single Exclusions tab

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Kubernetes Cluster                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │
│  │   Agent     │  │  Security   │  │  Backend    │               │
│  │ (DaemonSet) │  │  Scanner    │  │  (FastAPI)  │──┐            │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │            │
│         │                │                │         │            │
│         │    Pod failures & security      │         │            │
│         └────────────────┴────────────────┘         │            │
│                          │                          │            │
│                          ▼                          ▼            │
│                   ┌─────────────┐           ┌─────────────┐      │
│                   │ PostgreSQL  │           │  Frontend   │      │
│                   │  Database   │           │   (React)   │      │
│                   └─────────────┘           └─────────────┘      │
└──────────────────────────────────────────────────────────────────┘
                                                      │
                                                      ▼
                                              ┌─────────────┐
                                              │ LLM Provider│
                                              │ (External)  │
                                              └─────────────┘
```

**Components:**
- **Agent** — Watches Kubernetes API for pod failures, runs as DaemonSet
- **Security Scanner** — Audits pods for security misconfigurations
- **Backend** — FastAPI server, generates AI solutions, serves WebSocket updates
- **Frontend** — React dashboard with real-time updates
- **PostgreSQL** — Stores failure history and configuration

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

After installation, configure your LLM provider (OpenAI, Anthropic, Groq, or Google Gemini) via the Admin panel in the web dashboard to enable AI-powered solutions.

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
| **OpenAI** | `gpt-4.1-mini` | `gpt-4.1`, `gpt-4o` |
| **Anthropic** | `claude-sonnet-4-20250514` | `claude-opus-4-5-20251124`, `claude-haiku-4-5-20251015` |
| **Groq** | `llama-4-scout-17b-16e-instruct` | `llama-4-maverick-17b-128e-instruct`, `llama-3.3-70b-versatile` |
| **Google Gemini** | `gemini-2.0-flash` | `gemini-2.5-pro-preview-05-06`, `gemini-2.0-flash-lite` |

**Provider Aliases:** `claude` → `anthropic`, `groq_cloud` → `groq`, `google` → `gemini`

### Helm Values

Key configuration options in `values.yaml`:

```yaml
# Enable/disable components
agent:
  enabled: true
  clusterMetrics:
    enabled: true        # Enable cluster metrics collection
    interval: 30         # Collection interval in seconds

securityScanner:
  enabled: true          # Enable security scanning

postgresql:
  enabled: true          # Use built-in PostgreSQL

# LLM and notifications are configured via Admin Panel after installation
```

## Dashboard Features

### Pod Failures Tab
- Real-time pod failure detection
- AI-generated or rule-based solutions
- Expandable details with events, logs, and manifest
- Dismiss/restore functionality
- Retry AI solution generation

### Security Tab
- Security misconfiguration detection
- Severity-based filtering (Critical, High, Medium, Low)
- Detailed remediation steps
- Namespace-based organization

### Cluster Metrics Tab
- Real-time CPU, memory, and storage usage
- Node status and details
- Pod list with logs viewer
- Live log streaming with play/pause
- Namespace filtering

### Admin Panel
- **AI Config** - Configure AI provider (OpenAI, Anthropic, Groq, Google Gemini) for intelligent solutions
- **Notifications** - Configure Slack webhook for alerts
- **Exclusions** - Exclude namespaces from security scanning and pods from failure monitoring
- Real-time updates via WebSocket

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

### Common Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| Agent not detecting failures | No pods in dashboard | Check RBAC permissions: `kubectl auth can-i list pods --as=system:serviceaccount:kure-system:kure-monitor-agent` |
| No cluster metrics | Metrics tab shows loading | Install metrics-server or check agent logs |
| Backend connection errors | 500 errors in frontend | Verify PostgreSQL connection and network policies |
| LLM solutions not generating | Generic solutions only | Configure LLM provider via Admin panel |
| Storage metrics unavailable | N/A shown for storage | Ensure kubelet stats endpoint is accessible |

### Metrics Server Installation

For full cluster metrics (CPU/memory usage), install metrics-server:

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

## Security

- All components run as non-root users
- Network policies restrict inter-pod communication
- RBAC limits agent permissions to read-only pod access
- Security contexts prevent privilege escalation
- Container images are regularly scanned for vulnerabilities

## License

**Custom Non-Commercial License** — See [LICENSE](LICENSE) for full terms.

| Use Case | Allowed? |
|----------|----------|
| Personal homelab or learning | Yes |
| Internal company use (non-revenue) | Contact for permission |
| Selling or reselling Kure | No |
| Offering Kure as a managed service | No |
| Including in commercial products | No |

**Commercial licensing**: nano.code@outlook.com
