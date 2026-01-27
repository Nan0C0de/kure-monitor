# Kure Monitor

[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/kure-monitor)](https://artifacthub.io/packages/search?repo=kure-monitor)
[![Test Suite](https://github.com/Nan0C0de/kure-monitor/actions/workflows/test-suite.yml/badge.svg)](https://github.com/Nan0C0de/kure-monitor/actions/workflows/test-suite.yml)

**Kubernetes failure diagnosis with AI-powered troubleshooting**

Kure is a failure diagnosis tool that helps you understand **why** your Kubernetes workloads fail. When a pod crashes, gets stuck pending, or can't pull an image, Kure detects it instantly and provides AI-generated troubleshooting guidance to help you fix it fast.

## Why Kure?

Traditional monitoring tells you *that* something failed. Kure tells you *why* it failed and *how* to fix it:

- **Instant failure detection** — Know immediately when pods enter CrashLoopBackOff, ImagePullBackOff, Pending, or other failure states
- **AI-powered diagnosis** — Get contextual troubleshooting steps generated from pod events, logs, and manifest analysis
- **Security misconfiguration scanning** — Identify privileged containers, missing security contexts, and other security issues
- **All in one dashboard** — No context switching between kubectl, logs, and documentation

## What Kure is NOT

Kure is focused on failure diagnosis, not general observability:

- **Not a Prometheus replacement** — Kure doesn't collect time-series metrics or provide alerting rules
- **Not a full APM solution** — No distributed tracing, no service mesh integration
- **Not a log aggregator** — Logs are fetched on-demand for troubleshooting, not stored long-term

If you need comprehensive observability, use Kure alongside tools like Prometheus, Grafana, or Datadog.

## Features

- **Real-time Failure Detection** — Detects pod failures across all namespaces instantly
- **AI-Powered Troubleshooting** — Generates contextual solutions using OpenAI, Anthropic, Groq, or Google Gemini
- **Security Scanning** — Identifies security misconfigurations with remediation guidance
- **Live Pod Logs** — Stream logs in real-time with container selection
- **Cluster Overview** — CPU, memory, and storage usage at a glance
- **Notification Alerts** — Slack webhook integration for failure notifications
- **Admin Panel** — Configure AI provider, notifications, and exclusions via UI
- **Modern Dashboard** — Clean interface with dark/light mode support

## What's New in v1.5.0

- **Google Gemini Support** - New LLM provider with Gemini 2.5 Pro, 2.0 Flash, and 2.0 Flash Lite models
- **Redesigned Admin Panel** - New tabbed interface for better navigation (AI Config, Notifications, Exclusions)
- **Simplified Exclusions** - Security and Monitoring exclusions merged into single Exclusions tab

## Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Kure Agent      │───▶│ Kure Backend │───▶│ LLM Providers   │
│ (Pod Monitor)   │    │ (FastAPI)    │    │ OpenAI/Anthropic│
└─────────────────┘    └──────────────┘    └─────────────────┘
        │                      │
        │                      ▼
        │              ┌──────────────┐
        │              │ PostgreSQL   │
        │              │ Database     │
        │              └──────────────┘
        │
        ▼                      ▲
┌─────────────────┐            │
│ Kubernetes      │            │
│ API Server      │            │
└─────────────────┘            │
        ▲                      │
        │              ┌──────────────┐
┌─────────────────┐    │ Kure Frontend│
│ Security Scanner│    │ (React)      │
│ (Pod Auditor)   │───▶└──────────────┘
└─────────────────┘
```

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

## Development

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/Nan0C0de/kure-monitor.git
cd kure-monitor

# Backend
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm start

# Agent (requires kubectl configured)
cd agent
pip install -r requirements.txt
python main.py
```

### Running Tests

```bash
# Backend tests
cd backend && python -m pytest -v

# Frontend tests
cd frontend && npm test

# Agent tests
cd agent && python -m pytest -v

# Security scanner tests
cd security-scanner && python -m pytest -v
```

## Security

- All components run as non-root users
- Network policies restrict inter-pod communication
- RBAC limits agent permissions to read-only pod access
- Security contexts prevent privilege escalation
- Container images are regularly scanned for vulnerabilities

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## License

This project is licensed under a **Custom Non-Commercial License**. See the [LICENSE](LICENSE) file for full details.

### Key License Terms:

- **Free for non-commercial use** - Personal projects, education, open-source contributions
- **Commercial use requires permission** - Contact nano.code@outlook.com for licensing
- **Modifications allowed** - For non-commercial purposes only

**Commercial inquiries**: nano.code@outlook.com
