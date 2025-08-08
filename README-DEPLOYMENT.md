# Kure Kubernetes Deployment Guide

## Quick Start

1. **Update configuration:**
   ```bash
   # Edit k8s/configmap.yaml and set your LLM API key
   kubectl edit secret kure-secrets -n kure-system
   ```

2. **Build and deploy:**
   ```bash
   # Update REGISTRY in k8s/deploy.sh to your Docker registry
   ./k8s/deploy.sh
   ```

3. **Access the dashboard:**
   ```bash
   # Port-forward for local access
   kubectl port-forward svc/kure-frontend 8080:80 -n kure-system
   # Visit: http://localhost:8080
   ```

## Manual Deployment Steps

1. **Build Docker images:**
   ```bash
   docker build -t kure/backend:latest ./backend/
   docker build -t kure/agent:latest ./agent/
   docker build -t kure/frontend:latest ./frontend/
   ```

2. **Push to registry (if using external registry):**
   ```bash
   docker tag kure/backend:latest your-registry/kure/backend:latest
   docker push your-registry/kure/backend:latest
   # Repeat for agent and frontend
   ```

3. **Update image names in manifests:**
   ```bash
   # Edit k8s/*.yaml files to use your registry URLs
   ```

4. **Deploy to Kubernetes:**
   ```bash
   kubectl apply -f k8s/namespace.yaml
   kubectl apply -f k8s/configmap.yaml
   kubectl apply -f k8s/rbac.yaml
   kubectl apply -f k8s/backend.yaml
   kubectl apply -f k8s/agent.yaml
   kubectl apply -f k8s/frontend.yaml
   ```

## Configuration

### LLM Provider Setup
Edit `k8s/configmap.yaml` and set your LLM provider:

```yaml
stringData:
  KURE_LLM_PROVIDER: "groq"  # or openai, anthropic
  KURE_LLM_API_KEY: "your_actual_api_key_here"
  KURE_LLM_MODEL: "llama-3.1-8b-instant"
```

### Access Options

1. **LoadBalancer (Cloud providers):**
   ```bash
   kubectl get svc kure-frontend -n kure-system
   # Use EXTERNAL-IP
   ```

2. **NodePort:**
   ```bash
   # Change service type to NodePort in k8s/frontend.yaml
   kubectl get nodes -o wide
   # Access via NodeIP:NodePort
   ```

3. **Ingress:**
   ```bash
   # Configure your ingress controller and DNS
   # Update host in k8s/frontend.yaml
   ```

4. **Port Forward (Development):**
   ```bash
   kubectl port-forward svc/kure-frontend 8080:80 -n kure-system
   ```

## Monitoring

```bash
# Check pod status
kubectl get pods -n kure-system

# View logs
kubectl logs -l app=kure-backend -n kure-system
kubectl logs -l app=kure-agent -n kure-system
kubectl logs -l app=kure-frontend -n kure-system

# Check events
kubectl get events -n kure-system --sort-by=.metadata.creationTimestamp
```

## Troubleshooting

1. **Agent can't access Kubernetes API:**
   ```bash
   kubectl describe clusterrolebinding kure-agent
   kubectl get serviceaccount kure-agent -n kure-system
   ```

2. **Backend can't reach database:**
   ```bash
   kubectl get pvc -n kure-system
   kubectl describe pod -l app=kure-backend -n kure-system
   ```

3. **Frontend can't reach backend:**
   ```bash
   kubectl get svc -n kure-system
   kubectl port-forward svc/kure-backend 8000:8000 -n kure-system
   # Test: curl http://localhost:8000/health
   ```

## Scaling

```bash
# Scale components
kubectl scale deployment kure-backend --replicas=2 -n kure-system
kubectl scale deployment kure-frontend --replicas=2 -n kure-system

# Agent should stay at 1 replica to avoid duplicate monitoring
```