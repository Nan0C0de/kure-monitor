# Kure Monitor 🩺

[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/kure-monitor)](https://artifacthub.io/packages/search?repo=kure-monitor)

**Real-time Kubernetes monitoring with AI-powered diagnostics**

Kure is a comprehensive Kubernetes health monitoring system that detects pod failures in real-time and provides AI-generated solutions for quick troubleshooting. Built with a modern microservices architecture, it continuously watches your cluster and delivers actionable insights through an intuitive web dashboard.

## Features

- 🔍 **Real-time Pod Monitoring** - Detects failures across all namespaces instantly
- 🧠 **AI-Powered Solutions** - Generates contextual troubleshooting steps using LLMs
- 📊 **Modern Web Dashboard** - Clean interface with expandable failure details
- 🔒 **Secure by Design** - RBAC-compliant Alwith network policies and security contexts
- 🌐 **Multi-Provider LLM Support** - OpenAI, Anthropic, and Groq integration
- 🗄️ **PostgreSQL Backend** - Robust data persistence with full-text search
- ⚡ **Lightweight & Scalable** - Minimal resource footprint with horizontal scaling

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Kure Agent  │───▶│ Kure Backend │───▶│ LLM Providers   │
│ (DaemonSet) │    │ (FastAPI)    │    │ OpenAI/Anthropic│
└─────────────┘    └──────────────┘    └─────────────────┘
       │                    │
       │                    ▼
       │            ┌──────────────┐
       │            │ PostgreSQL   │
       │            │ Database     │
       │            └──────────────┘
       │
       ▼                    ▲
┌─────────────┐            │
│ Kubernetes  │            │
│ API Server  │            │
└─────────────┘            │
                           │
                    ┌──────────────┐
                    │ Kure Frontend│
                    │ (React)      │
                    └──────────────┘
```

## Quick Start

### Prerequisites
- Kubernetes cluster (1.20+)
- kubectl configured
- Docker (for building images)

### Deploy to Kubernetes

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/kure.git
   cd kure
   ```

2. **Deploy with Helm** (recommended)
   ```bash
   # Add the Helm repository
   helm repo add kure https://igorkoricanac.github.io/kure
   helm repo update
   
   # Install with custom LLM configuration
   helm install kure kure/kure --namespace kure-system --create-namespace \
     --set backend.env.KURE_LLM_PROVIDER=openai \
     --set backend.env.KURE_LLM_API_KEY=your_api_key_here \
     --set backend.env.KURE_LLM_MODEL=gpt-4o-mini
   ```

3. **Access the dashboard**
   ```bash
   # Via NodePort (if using Helm default)
   kubectl get svc kure-frontend -n kure-system
   # Access via http://localhost:<nodePort>
   
   # OR via port-forward
   kubectl port-forward svc/kure-frontend 8080:8080 -n kure-system
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

## Monitoring and Troubleshooting

### Check System Status
```bash
# Pod status
kubectl get pods -n kure-system

# View logs
kubectl logs -l app=kure-backend -n kure-system
kubectl logs -l app=kure-agent -n kure-system
kubectl logs -l app=kure-frontend -n kure-system
```

### Common Issues

| Issue | Symptom | Solution |
|-------|---------|----------|
| Agent not detecting failures | No pods in dashboard | Check RBAC permissions: `kubectl describe clusterrolebinding kure-agent` |
| Backend connection errors | 500 errors in frontend | Verify PostgreSQL connection and network policies |
| Frontend loading issues | Blank dashboard | Check service connectivity: `kubectl get svc -n kure-system` |
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
- ❌ **Commercial use requires permission** - Contact igor.koricanac@gmail.com for licensing
- ✅ **Modifications allowed** - For non-commercial purposes only
- 📧 **Commercial inquiries**: igor.koricanac@gmail.com

**Summary**: You can freely use, modify, and distribute this software for non-commercial purposes. Commercial use, including in products or services that generate revenue, requires a separate commercial license.
