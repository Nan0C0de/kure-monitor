# Kure Monitor 🩺

[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/kure-monitor)](https://artifacthub.io/packages/search?repo=kure-monitor)

**Real-time Kubernetes monitoring with AI-powered diagnostics**

Kure is a comprehensive Kubernetes health monitoring system that detects pod failures in real-time and provides AI-generated solutions for quick troubleshooting. Built with a modern microservices architecture, it continuously watches your cluster and delivers actionable insights through an intuitive web dashboard.

## Features

- 🔍 **Real-time Pod Monitoring** - Detects failures across all namespaces instantly
- 🛡️ **Security Scanning** - Real-time detection of security misconfigurations and vulnerabilities
- 🧠 **AI-Powered Solutions** - Generates contextual troubleshooting steps using LLMs
- 📊 **Modern Web Dashboard** - Clean interface with expandable failure details
- ⚙️ **Admin Panel** - Manage namespace exclusions in real-time
- 🔒 **Secure by Design** - RBAC-compliant with network policies and security contexts
- 🌐 **Multi-Provider LLM Support** - OpenAI, Anthropic, and Groq integration
- 🗄️ **PostgreSQL Backend** - Robust data persistence with full-text search
- ⚡ **Lightweight & Scalable** - Minimal resource footprint with horizontal scaling

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
- Docker (for building images)

### Deploy to Kubernetes

1. **Clone the repository**
   ```bash
   git clone https://github.com/Nan0C0de/kure-monitor.git
   cd kure-monitor
   ```

2. **Deploy with Helm** (recommended)
   ```bash
   # Add the Helm repository
   helm repo add kure-monitor https://nan0c0de.github.io/kure-monitor/
   helm repo update
   
   # Install with custom LLM configuration
   helm install kure-monitor kure-monitor/kure \
     --set backend.env.KURE_LLM_PROVIDER=openai \
     --set backend.env.KURE_LLM_API_KEY=your_api_key_here \
     --set backend.env.KURE_LLM_MODEL=gpt-4o-mini
   ```

3. **Access the dashboard**
   ```bash
   # Via NodePort (if using Helm default)
   kubectl get svc
   # Access via http://localhost:<nodePort>
   
   # OR via port-forward
   kubectl port-forward svc/kure-monitor-frontend 8080:8080
   # Open http://localhost:8080
   ```

## Configuration

### Environment Variables

| Variable | Component | Description | Default | Required |
|----------|-----------|-------------|---------|----------|
| `KURE_LLM_PROVIDER` | Backend | LLM provider (`openai`, `anthropic`, `groq`) | None | Yes* |
| `KURE_LLM_API_KEY` | Backend | API key for chosen LLM provider | None | Yes* |
| `KURE_LLM_MODEL` | Backend | Specific model to use | None | Yes* |
| `DATABASE_URL` | Backend | PostgreSQL connection string | Auto-generated | Yes** |
| `CLUSTER_NAME` | Agent | Kubernetes cluster identifier | `k8s-cluster` | No |
| `CHECK_INTERVAL` | Agent | Pod check interval (seconds) | `30` | No |

\* All three LLM values (PROVIDER, API_KEY, MODEL) must be provided together for AI functionality, or all omitted to use rule-based solutions only  
\** Auto-generated if using included PostgreSQL deployment

### Supported LLM Providers

| Provider | Default Model | Alternative Models | Setup |
|----------|---------------|-----------------------|-------|
| **OpenAI** | `gpt-4o-mini` | `gpt-4o`, `gpt-4`, `gpt-3.5-turbo` | Set `KURE_LLM_PROVIDER=openai` |
| **Anthropic** | `claude-3-haiku-20240307` | `claude-3-sonnet-20240229`, `claude-3-opus-20240229` | Set `KURE_LLM_PROVIDER=anthropic` |
| **Groq** | `llama-3.1-8b-instant` | `mixtral-8x7b-32768`, `llama-3.1-70b-versatile` | Set `KURE_LLM_PROVIDER=groq` |

**Provider Aliases:** `claude` → `anthropic`, `groq_cloud` → `groq`

## Admin Panel

The Admin Panel allows you to manage namespace exclusions in real-time:

- **Exclude Namespaces** - Prevent specific namespaces from being monitored
- **Include Namespaces** - Re-enable monitoring for previously excluded namespaces
- **Real-time Updates** - Changes take effect immediately via WebSocket notifications
- **Namespace Suggestions** - Shows available namespaces with active findings

System namespaces (`kube-system`, `kube-public`, `kube-node-lease`) are always excluded by default.

## Monitoring and Troubleshooting

### Check System Status
```bash
# Pod status
kubectl get pods

# View logs
kubectl logs -l app.kubernetes.io/component=backend
kubectl logs -l app.kubernetes.io/component=agent
kubectl logs -l app.kubernetes.io/component=security-scanner
kubectl logs -l app.kubernetes.io/component=frontend
```

### Common Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| Agent not detecting failures | No pods in dashboard | Check RBAC permissions: `kubectl describe clusterrolebinding` |
| Backend connection errors | 500 errors in frontend | Verify PostgreSQL connection and network policies |
| Frontend loading issues | Blank dashboard | Check service connectivity: `kubectl get svc` |
| LLM solutions not generating | Generic solutions only | Verify API key and provider configuration |

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

## Security

- All components run as non-root users
- Network policies restrict inter-pod communication
- RBAC limits agent permissions to read-only pod access
- Security contexts prevent privilege escalation
- Container images are regularly scanned for vulnerabilities

## License

This project is licensed under a **Custom Non-Commercial License**. See the [LICENSE](LICENSE) file for full details.

### Key License Terms:

- ✅ **Free for non-commercial use** - Personal projects, education, open-source contributions
- ❌ **Commercial use requires permission** - Contact nano.code@outlook.com for licensing
- ✅ **Modifications allowed** - For non-commercial purposes only
- 📧 **Commercial inquiries**: nano.code@outlook.com

**Summary**: You can freely use, modify, and distribute this software for non-commercial purposes. Commercial use, including in products or services that generate revenue, requires a separate commercial license.
