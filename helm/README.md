# Kure Helm Chart

A Kubernetes health monitoring system with intelligent failure detection and solution recommendations.

## Installation

```bash
# Install in kure-system namespace
helm install kure-monitor kure-monitor/kure --version 1.0.0 --create-namespace --namespace kure-system \
  --set backend.env.KURE_LLM_PROVIDER=openai \
  --set backend.env.KURE_LLM_API_KEY=your_api_key_here \
  --set backend.env.KURE_LLM_MODEL=gpt-4o-mini
```

## Configuration

Key configuration options in `values.yaml`:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.namespace` | Kubernetes namespace | `kure-system` |
| `global.imageRegistry` | Image registry override | `""` |
| `agent.image.repository` | Agent image repository | `ghcr.io/nan0c0de/kure-monitor/agent` |
| `agent.image.tag` | Agent image tag | `1.0.0` |
| `agent.serviceAccount.name` | Service account name | `kure-agent` |
| `backend.replicaCount` | Backend replica count | `1` |
| `backend.image.repository` | Backend image repository | `ghcr.io/nan0c0de/kure-monitor/backend` |
| `backend.image.tag` | Backend image tag | `1.0.0` |
| `backend.service.type` | Backend service type | `ClusterIP` |
| `backend.service.port` | Backend service port | `8000` |
| `backend.env.KURE_LLM_PROVIDER` | LLM provider (openai/anthropic/groq) | `""` |
| `backend.env.KURE_LLM_API_KEY` | LLM API key | `""` |
| `backend.env.KURE_LLM_MODEL` | LLM model name | `""` |
| `frontend.replicaCount` | Frontend replica count | `1` |
| `frontend.image.repository` | Frontend image repository | `ghcr.io/nan0c0de/kure-monitor/frontend` |
| `frontend.image.tag` | Frontend image tag | `1.0.0` |
| `frontend.service.type` | Frontend service type | `NodePort` |
| `frontend.service.port` | Frontend service port | `8080` |
| `frontend.service.nodePort` | Frontend NodePort | `30080` |
| `ingress.enabled` | Enable ingress | `false` |
| `ingress.className` | Ingress class name | `""` |
| `postgresql.external` | Use external PostgreSQL | `false` |
| `postgresql.host` | PostgreSQL host (external only) | `""` |
| `postgresql.port` | PostgreSQL port | `5432` |
| `postgresql.database` | PostgreSQL database name | `kure` |
| `postgresql.username` | PostgreSQL username | `kure` |
| `postgresql.password` | PostgreSQL password | `kure-password-change-me` |
| `postgresql.persistence.enabled` | Enable PostgreSQL persistence | `true` |
| `postgresql.persistence.size` | PostgreSQL storage size | `10Gi` |
| `podSecurityStandards.enforce` | Pod Security Standard enforcement level | `restricted` |
| `securityContext.runAsNonRoot` | Run containers as non-root user | `true` |
| `securityContext.runAsUser` | User ID to run containers | `1001` |

## Components

- **Agent**: Monitors Kubernetes pods for failures
- **Backend**: FastAPI server with solution engine
- **Frontend**: React dashboard for cluster health
- **PostgreSQL**: Database for storing failure reports

## Requirements

- Kubernetes 1.19+
- Helm 3.0+

## Uninstall

```bash
helm uninstall kure-monitor --namespace kure-system
```