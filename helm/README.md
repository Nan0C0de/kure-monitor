# Kure Helm Chart

A Kubernetes health monitoring system with AI-powered diagnostics, real-time cluster metrics, and security scanning.

## Quick Start

> **Important:** Do not use the default install command from the modal. Use the command below to install with the required namespace and AI configuration.

```bash
# Add the Helm repository
helm repo add kure-monitor https://nan0c0de.github.io/kure-monitor/
helm repo update

# Install Kure Monitor
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set backend.env.KURE_LLM_PROVIDER=openai \
  --set backend.env.KURE_LLM_API_KEY=your_api_key_here \
  --set backend.env.KURE_LLM_MODEL=gpt-4o-mini
```

## Features

- Real-time pod failure detection and monitoring
- AI-powered troubleshooting solutions (OpenAI, Anthropic, Groq)
- Cluster metrics dashboard (CPU, memory, storage)
- Live pod log streaming
- Security misconfiguration scanning
- Slack and Microsoft Teams notifications
- Admin panel for namespace/pod exclusions

## Installation Options

### With OpenAI (Recommended)
```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set backend.env.KURE_LLM_PROVIDER=openai \
  --set backend.env.KURE_LLM_API_KEY=your_api_key_here \
  --set backend.env.KURE_LLM_MODEL=gpt-4o-mini
```

### With Anthropic Claude
```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set backend.env.KURE_LLM_PROVIDER=anthropic \
  --set backend.env.KURE_LLM_API_KEY=your_api_key_here \
  --set backend.env.KURE_LLM_MODEL=claude-3-haiku-20240307
```

### With Groq (Free Tier Available)
```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set backend.env.KURE_LLM_PROVIDER=groq \
  --set backend.env.KURE_LLM_API_KEY=your_api_key_here \
  --set backend.env.KURE_LLM_MODEL=llama-3.1-8b-instant
```

### Without AI (Rule-based Solutions)
```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace
```

## Configuration

### Core Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `agent.enabled` | Enable pod monitoring agent | `true` |
| `agent.clusterMetrics.enabled` | Enable cluster metrics collection | `true` |
| `agent.image.tag` | Agent image tag | `1.4.0` |
| `securityScanner.enabled` | Enable security scanner | `true` |
| `securityScanner.image.tag` | Security scanner image tag | `1.4.0` |
| `backend.replicaCount` | Backend replica count | `1` |
| `backend.image.tag` | Backend image tag | `1.4.0` |
| `frontend.image.tag` | Frontend image tag | `1.4.0` |

### LLM Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `backend.env.KURE_LLM_PROVIDER` | LLM provider (`openai`, `anthropic`, `groq`) | `""` |
| `backend.env.KURE_LLM_API_KEY` | LLM API key | `""` |
| `backend.env.KURE_LLM_MODEL` | LLM model name | `""` |

**Note:** All three LLM values must be provided together, or all empty to use rule-based solutions.

### Service Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `backend.service.type` | Backend service type | `ClusterIP` |
| `backend.service.port` | Backend service port | `8000` |
| `frontend.service.type` | Frontend service type | `NodePort` |
| `frontend.service.port` | Frontend service port | `8080` |
| `frontend.service.nodePort` | Frontend NodePort | `30080` |

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

## Requirements

- Kubernetes 1.20+
- Helm 3.0+
- (Optional) metrics-server for CPU/memory metrics

## Upgrade

```bash
helm repo update
helm upgrade kure-monitor kure-monitor/kure --version 1.4.0 -n kure-system
```

## Uninstall

```bash
helm uninstall kure-monitor -n kure-system
```

## License

Custom Non-Commercial License. See [LICENSE](https://github.com/Nan0C0de/kure-monitor/blob/main/LICENSE) for details.
