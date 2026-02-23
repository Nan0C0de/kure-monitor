# Contributing to Kure Monitor

Thank you for your interest in contributing to Kure Monitor!

## Reporting Bugs

1. Check [existing issues](https://github.com/Nan0C0de/kure-monitor/issues) to avoid duplicates
2. Open a new issue using the **Bug Report** template
3. Include:
   - Kure Monitor version
   - Kubernetes version
   - Steps to reproduce
   - Expected vs actual behavior
   - Relevant logs (backend, agent, frontend)

## Suggesting Features

1. Check [existing issues](https://github.com/Nan0C0de/kure-monitor/issues) for similar requests
2. Open a new issue using the **Feature Request** template
3. Describe the problem you're trying to solve and your proposed solution

## Local Development Setup

### Prerequisites

- Docker (for building images)
- A Kubernetes cluster (minikube, kind, k3s, or a remote cluster)
- `kubectl` configured to talk to your cluster

### 1. Clone the Repository

```bash
git clone https://github.com/Nan0C0de/kure-monitor.git
cd kure-monitor
```

### 2. Build Docker Images

Build all four component images locally. If you're using minikube, run `eval $(minikube docker-env)` first so images are available inside the cluster.

```bash
docker build -t kure-backend:dev ./backend
docker build -t kure-frontend:dev ./frontend
docker build -t kure-agent:dev ./agent
docker build -t kure-security-scanner:dev ./security-scanner
```

### 3. Create the Namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

### 4. Create Secrets

The k8s manifests reference three secrets. Create them before deploying.

**PostgreSQL secret** (database credentials):

```bash
kubectl apply -f k8s/postgresql.yaml
```

> This file contains the `postgresql-secret` Secret, the `postgresql-config` ConfigMap, the PostgreSQL Deployment, Service, and PVC. Review `k8s/postgresql.yaml` and change `POSTGRES_PASSWORD` from the default before deploying to a shared cluster.

**Encryption secret** (used by the backend to encrypt stored LLM API keys):

```bash
# Generate a key
ENCRYPTION_KEY=$(python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")

# Edit k8s/encryption-secret.yaml and replace REPLACE_ME_WITH_GENERATED_KEY with your key
# Then apply:
kubectl apply -f k8s/encryption-secret.yaml
```

**Auth secret** (optional — only needed if you want to enable dashboard authentication):

```bash
# Generate an API key
API_KEY=$(openssl rand -base64 32)

# Create the secret
kubectl create secret generic kure-auth-secret \
  --namespace kure-system \
  --from-literal=api-key="$API_KEY"
```

If you skip this step, authentication is disabled and the dashboard is fully open. The agent and scanner manifests reference this secret with `optional: true`, so they will start fine without it.

### 5. Apply RBAC and ConfigMap

```bash
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/configmap.yaml
```

### 6. Update Image References in Manifests

The k8s manifests use placeholder image names (`BACKEND_IMAGE`, `FRONTEND_IMAGE`, etc.). Replace them with your local image tags:

```bash
# On Linux/macOS:
sed -i 's|image: BACKEND_IMAGE|image: kure-backend:dev|' k8s/backend.yaml
sed -i 's|image: FRONTEND_IMAGE|image: kure-frontend:dev|' k8s/frontend.yaml
sed -i 's|image: AGENT_IMAGE|image: kure-agent:dev|' k8s/agent.yaml
sed -i 's|image: SECURITY_SCANNER_IMAGE|image: kure-security-scanner:dev|' k8s/security-scanner.yaml
```

> **Tip:** Don't commit these image name changes. Use `git checkout -- k8s/` to revert them when done.

### 7. Deploy All Components

```bash
kubectl apply -f k8s/backend.yaml
kubectl apply -f k8s/frontend.yaml
kubectl apply -f k8s/agent.yaml
kubectl apply -f k8s/security-scanner.yaml
```

Optionally apply network policies and the ServiceMonitor:

```bash
kubectl apply -f k8s/network-policies.yaml
kubectl apply -f k8s/servicemonitor.yaml    # requires Prometheus Operator
```

### 8. Verify Everything Is Running

```bash
kubectl get pods -n kure-system
```

All pods should reach `Running` status. If a pod is stuck, check logs:

```bash
kubectl logs -l app=kure-backend -n kure-system
kubectl logs -l app=kure-agent -n kure-system
kubectl logs -l app=kure-security-scanner -n kure-system
```

### 9. Access the Dashboard

```bash
kubectl port-forward svc/kure-frontend 8080:8080 -n kure-system
# Open http://localhost:8080
```

### Iterating on Changes

After modifying code in a component, rebuild its image and restart the pod:

```bash
# Example: rebuilding the backend
docker build -t kure-backend:dev ./backend
kubectl rollout restart deployment/kure-monitor-backend -n kure-system
```

### Running Tests Locally

```bash
# Backend
cd backend && python -m pytest -v

# Frontend
cd frontend && npm test

# Agent
cd agent && python -m pytest -v
```

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
