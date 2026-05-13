---
title: Installation
description: Install Kure Monitor on your Kubernetes cluster with Helm, with cloud-specific notes for EKS, GKE, AKS, Minikube, and Kind.
---

This guide covers how to install Kure Monitor on your Kubernetes cluster. Kure ships as a Helm chart; raw `k8s/` manifests are no longer maintained.

## Prerequisites

- Kubernetes cluster (1.20+)
- `kubectl` configured to access your cluster
- Helm 3.x
- Cluster admin permissions

## Helm install

### Add the repository

```bash
helm repo add kure-monitor https://nan0c0de.github.io/kure-monitor/
helm repo update
```

### Basic install

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)"
```

### Install with custom values

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)" \
  --set frontend.service.type=LoadBalancer
```

### Install from a local checkout

```bash
git clone https://github.com/Nan0C0de/kure-monitor.git
cd kure-monitor
helm install kure-monitor ./helm \
  --namespace kure-system \
  --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)"
```

## Post-install

### 1. Verify

```bash
kubectl get pods -n kure-system
```

Expected:

```
NAME                                             READY   STATUS    RESTARTS   AGE
kure-monitor-agent-xxxxx                         1/1     Running   0          1m
kure-monitor-backend-xxxxx                       1/1     Running   0          1m
kure-monitor-frontend-xxxxx                      1/1     Running   0          1m
kure-monitor-security-scanner-xxxxx              1/1     Running   0          1m
postgresql-xxxxx                                 1/1     Running   0          1m
```

### 2. Access the dashboard

**Port-forward (development):**

```bash
kubectl port-forward svc/kure-monitor-frontend 8080:8080 -n kure-system
# http://localhost:8080
```

**NodePort:**

```bash
kubectl get svc kure-monitor-frontend -n kure-system
# http://<node-ip>:30080
```

**LoadBalancer:**

```bash
helm upgrade kure-monitor kure-monitor/kure \
  --set frontend.service.type=LoadBalancer \
  -n kure-system
```

**Ingress:**

```bash
helm upgrade kure-monitor kure-monitor/kure \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=kure.example.com \
  -n kure-system
```

### 3. Create the initial admin

On first visit, the dashboard prompts you to create the initial **admin** account (username + password). After signing in, go to **Admin → Users** to invite further users with `read`, `write`, or `admin` roles.

Authentication is always on in 2.3+ and is wired up automatically by the Helm chart — there is nothing to configure at install time. The legacy `auth.apiKey` single-key model was removed in 2.3.0. See [Authentication](/kure-monitor/configuration/authentication/) and the [2.2 → 2.3 migration guide](/kure-monitor/migration/2-2-to-2-3/) for details.

### 4. Configure an LLM provider

1. Open the dashboard
2. Go to **Admin Panel → AI Configuration**
3. Pick a provider (OpenAI, Anthropic, Groq, Gemini, GitHub Copilot, or Ollama)
4. Enter your API key
5. Pick a model
6. Click **Test Connection**, then **Save**

See [LLM Providers](/kure-monitor/configuration/llm-providers/) for the full list of supported models.

## Upgrading

```bash
helm repo update
helm upgrade kure-monitor kure-monitor/kure -n kure-system
```

## Uninstalling

```bash
helm uninstall kure-monitor -n kure-system
kubectl delete namespace kure-system   # removes all data
```

## Cloud-specific notes

### Amazon EKS

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)" \
  --set frontend.service.type=LoadBalancer \
  --set frontend.service.annotations."service\.beta\.kubernetes\.io/aws-load-balancer-type"=nlb
```

Requires the AWS Load Balancer Controller for `LoadBalancer` services.

### Google GKE

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)" \
  --set frontend.service.type=LoadBalancer
```

### Azure AKS

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)" \
  --set frontend.service.type=LoadBalancer
```

### Minikube

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)"
minikube service kure-monitor-frontend -n kure-system
```

### Kind

```bash
helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)"
kubectl port-forward svc/kure-monitor-frontend 8080:8080 -n kure-system
```

## Next steps

- [Quick Start](/kure-monitor/getting-started/quick-start/) — fastest path to a working install
- [Configuration overview](/kure-monitor/configuration/overview/) — Helm values reference
- [Troubleshooting](/kure-monitor/reference/troubleshooting/) — common install issues
