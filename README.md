# Kure Monitor

[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/kure-monitor)](https://artifacthub.io/packages/search?repo=kure-monitor)
[![Test Suite](https://github.com/Nan0C0de/kure-monitor/actions/workflows/test-suite.yml/badge.svg)](https://github.com/Nan0C0de/kure-monitor/actions/workflows/test-suite.yml)

**Real-time Kubernetes monitoring with AI-powered diagnostics**

Kure is a comprehensive Kubernetes health monitoring system that detects pod failures in real-time and provides AI-generated solutions for quick troubleshooting. Built with a modern microservices architecture, it continuously watches your cluster and delivers actionable insights through an intuitive web dashboard.

## Features

- **Real-time Pod Monitoring** - Detects failures across all namespaces instantly
- **Cluster Metrics Dashboard** - Live CPU, memory, storage usage with node details
- **Security Scanning** - Real-time detection of security misconfigurations and vulnerabilities
- **AI-Powered Solutions** - Generates contextual troubleshooting steps using LLMs
- **Live Pod Logs** - Stream logs in real-time with container selection
- **Notification System** - Slack webhook integration for instant alerts
- **Admin Panel** - Manage namespace and pod exclusions in real-time
- **Modern Web Dashboard** - Clean interface with dark/light mode support
- **Secure by Design** - RBAC-compliant with network policies and security contexts
- **Multi-Provider LLM Support** - OpenAI, Anthropic, and Groq integration
- **PostgreSQL Backend** - Robust data persistence with full-text search

## What's New in v1.4.1

- **Pod Metrics Viewing** - View CPU and memory usage per pod with historical charts
- **Node Details Modal** - Detailed node view with progress bars and conditions
- **Enhanced Monitoring Tab** - CPU/Memory columns in pod table with Metrics button
- **Metrics History** - Backend stores last 15 data points for trend analysis
- **Recharts Integration** - Beautiful line charts for metrics visualization
- **LLM Configuration via UI** - Configure AI provider (OpenAI, Anthropic, Groq) through Admin panel - no API key required at install time
- **Setup Banner** - Prompts users to configure AI on first run
- **Security Fixes** - Init containers now have resource limits, namespace includes PSA labels

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

# Install with AI-powered solutions
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set backend.env.KURE_LLM_PROVIDER=openai \
  --set backend.env.KURE_LLM_API_KEY=your_api_key_here \
  --set backend.env.KURE_LLM_MODEL=gpt-4o-mini
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

### Environment Variables

| Variable | Component | Description | Default |
|----------|-----------|-------------|---------|
| `KURE_LLM_PROVIDER` | Backend | LLM provider (`openai`, `anthropic`, `groq`) | None |
| `KURE_LLM_API_KEY` | Backend | API key for chosen LLM provider | None |
| `KURE_LLM_MODEL` | Backend | Specific model to use | Provider default |
| `DATABASE_URL` | Backend | PostgreSQL connection string | Auto-generated |

**Note:** All three LLM values must be provided together for AI functionality, or all omitted to use rule-based solutions only.

### Supported LLM Providers

| Provider | Default Model | Alternative Models |
|----------|---------------|--------------------|
| **OpenAI** | `gpt-4o-mini` | `gpt-4o`, `gpt-4`, `gpt-3.5-turbo` |
| **Anthropic** | `claude-3-haiku-20240307` | `claude-3-sonnet-20240229`, `claude-3-opus-20240229` |
| **Groq** | `llama-3.1-8b-instant` | `mixtral-8x7b-32768`, `llama-3.1-70b-versatile` |

**Provider Aliases:** `claude` → `anthropic`, `groq_cloud` → `groq`

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

# Notification settings (configure via Admin Panel)
backend:
  env:
    KURE_LLM_PROVIDER: ""
    KURE_LLM_API_KEY: ""
    KURE_LLM_MODEL: ""
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
- **Namespace Exclusions** - Exclude namespaces from security scanning
- **Pod Exclusions** - Exclude pods from failure monitoring
- **Notification Settings** - Configure Slack webhook for alerts
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
| LLM solutions not generating | Generic solutions only | Verify API key and provider configuration |
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
