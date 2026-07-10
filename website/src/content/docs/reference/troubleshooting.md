---
title: Troubleshooting
description: Common issues and fixes — install, auth, dashboard, AI, security scanner, mirror pods, network, upgrades.
---

Common issues with Kure Monitor and how to fix them.

## Install issues

### Pods not starting

```bash
kubectl get pods -n kure-system
kubectl describe pod <pod-name> -n kure-system
```

| Issue | Fix |
|-------|-----|
| Insufficient resources | Reduce resource requests in `values.yaml` |
| Image pull errors | Check registry access and image tags |
| PVC pending | Ensure StorageClass exists with available capacity |
| RBAC issues | Verify ClusterRole and ClusterRoleBinding were created |

### PostgreSQL connection failed

```bash
kubectl get pods -n kure-system -l app=postgresql
kubectl logs   -n kure-system -l app=postgresql
kubectl get svc -n kure-system | grep postgres
kubectl get secret -n kure-system kure-secrets -o yaml
kubectl get pvc -n kure-system
```

### Image pull errors

```bash
docker pull ghcr.io/igor-koricanac/kure-monitor/backend:2.4.0

# Private registry
kubectl create secret docker-registry regcred \
  --docker-server=ghcr.io \
  --docker-username=<user> \
  --docker-password=<token> \
  -n kure-system
```

```yaml
imagePullSecrets:
  - name: regcred
```

## Authentication issues

### Dashboard goes straight to main page (no login)

Auth is always on in 2.3+. If no login page appears, the bootstrap Secret is missing.

```bash
kubectl get secret kure-monitor-bootstrap -n kure-system

# If missing (e.g., manifest install)
kubectl create secret generic kure-monitor-bootstrap -n kure-system \
  --from-literal=service-token="$(openssl rand -hex 32)" \
  --from-literal=session-secret="$(openssl rand -hex 32)"

kubectl rollout restart deployment/kure-monitor-backend -n kure-system
```

### 401 Unauthorized on API calls

Verify your session cookie or service token. From the browser, inspect cookies (`kure_session` should be set after login). From the agent / scanner, confirm `X-Service-Token` is in the request:

```bash
kubectl logs -n kure-system -l app=kure-backend | grep -i auth
```

### Agent / scanner getting 401s

Ingest endpoints (`POST /api/pods/failed`, etc.) require `X-Service-Token`, not user auth. Confirm:

```bash
# Should return 400 (bad body), NOT 401
curl -X POST http://localhost:8000/api/pods/failed \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: $SERVICE_TOKEN" \
  -d '{}'
```

If you see 401, the service token in the agent/scanner pod doesn't match the backend's. Confirm both mount the same `<release>-bootstrap` Secret.

### WebSocket rejected

- Confirm you're logged in
- Check browser console for WebSocket errors
- Confirm the session cookie exists

## Dashboard issues

### Cannot access dashboard

```bash
kubectl get svc kure-monitor-frontend -n kure-system
```

By service type:

```bash
# NodePort
kubectl get nodes -o wide
kubectl get svc kure-monitor-frontend -n kure-system \
  -o jsonpath='{.spec.ports[0].nodePort}'

# Port-forward
kubectl port-forward svc/kure-monitor-frontend 8080:8080 -n kure-system

# LoadBalancer
kubectl get svc kure-monitor-frontend -n kure-system -w
```

### Dashboard stuck on "Connecting..."

```bash
kubectl port-forward svc/kure-monitor-backend 8000:8000 -n kure-system
curl http://localhost:8000/api/config

kubectl logs -n kure-system -l app=kure-frontend
```

Common causes: backend not ready, CORS misconfig, NetworkPolicy blocking traffic.

### No pod failures showing

```bash
kubectl get pods -n kure-system -l app=kure-agent
kubectl logs   -n kure-system -l app=kure-agent

# Confirm agent can reach backend
kubectl exec -n kure-system -l app=kure-agent -- \
  curl -s http://kure-monitor-backend:8000/api/config
```

Also check **Admin → Suppressions** — the namespace may be excluded.

## AI / LLM issues

### "AI Not Configured" banner

**Admin → AI Configuration** → pick provider → key → model → Test → Save. See [LLM Providers](/kure-monitor/configuration/llm-providers/).

### Test connection failed

| Error | Fix |
|-------|-----|
| Invalid API key | Re-check the key |
| Rate limited | Wait and retry, or use a different key |
| Model not available | Pick another model |
| Network error | Confirm backend can reach the LLM API |

```bash
kubectl exec -n kure-system -l app=kure-backend -- \
  curl -s https://api.openai.com
```

### AI solutions not generating

```bash
curl http://localhost:8000/api/admin/llm/status
kubectl logs -n kure-system -l app=kure-backend | grep -i llm
```

If LLM fails, Kure falls back to rule-based solutions. Generic but functional.

## Security scanner issues

### No security findings

```bash
kubectl get pods -n kure-system -l app=kure-security-scanner
kubectl logs   -n kure-system -l app=kure-security-scanner
```

Also check **Admin → Suppressions** for excluded namespaces.

### Too many findings from system namespaces

Add to **Admin → Suppressions**:

- `kube-system`
- `kube-public`
- `kube-node-lease`
- `kure-system`

## Mirror pod issues

### "Test Fix" button missing

- Logged in as `read` / `write` (admin only)
- The pod has no AI solution yet

### Mirror pod fails to deploy

| Issue | Fix |
|-------|-----|
| RBAC missing | Backend ClusterRole needs `create`, `delete` on `pods` |
| Quota exceeded | Check `ResourceQuota` in the namespace |
| Image pull error | Mirror uses the same image as the original |

```bash
kubectl get clusterrole -l app.kubernetes.io/component=backend -o yaml | grep -A5 "resources.*pods"
kubectl logs -n kure-system -l app.kubernetes.io/component=backend | grep -i mirror
```

### Stuck in `Pending`

- Mirror inherits resource requests from the original — confirm node capacity
- Original may have node selectors / affinity that can't be satisfied
- `kubectl describe pod <mirror-pod-name> -n <namespace>`

### Not auto-deleting

- Backend pod isn't running (cleanup is a background task)
- Backend logs may show cleanup errors
- Manual: `kubectl delete pod <mirror-pod-name> -n <namespace>`
- TTL setting: **Admin → Settings**

## Performance issues

### High memory usage / OOMKilled

```yaml
backend:
  resources:
    limits:
      memory: 2Gi

agent:
  resources:
    limits:
      memory: 1Gi
```

### Slow dashboard

- Filter by namespace
- Dismiss resolved failures
- Check browser console for errors

### Agent using too much CPU

```yaml
agent:
  checkInterval: 30  # bump from default
```

## Network issues

### NetworkPolicies blocking traffic

```bash
kubectl get networkpolicies -n kure-system
kubectl delete networkpolicy -n kure-system --all   # debug only
```

### DNS failures

```bash
kubectl exec -n kure-system -l app=kure-agent -- \
  nslookup kure-monitor-backend.kure-system.svc.cluster.local
```

## Upgrade issues

### Database migration failed

```bash
kubectl logs -n kure-system -l app=kure-backend | grep -i migration

kubectl exec -n kure-system -l app=postgresql -- \
  psql -U kure -d kure -c "SELECT version FROM schema_migrations;"
```

### Helm upgrade fails

```bash
helm list -n kure-system
helm history kure-monitor -n kure-system
helm rollback kure-monitor <revision> -n kure-system
helm upgrade kure-monitor kure-monitor/kure -n kure-system --force
```

## Logging and debugging

### Enable debug logging

```bash
kubectl set env deployment/kure-monitor-backend -n kure-system LOG_LEVEL=DEBUG
kubectl set env daemonset/kure-monitor-agent     -n kure-system KURE_LOG_LEVEL=DEBUG
```

### View logs

```bash
# All components
kubectl logs -n kure-system \
  -l app.kubernetes.io/instance=kure-monitor --all-containers

# Per component
kubectl logs -n kure-system -l app=kure-backend          -f
kubectl logs -n kure-system -l app=kure-agent            -f
kubectl logs -n kure-system -l app=kure-frontend         -f
kubectl logs -n kure-system -l app=kure-security-scanner -f
```

### Diagnostics bundle

```bash
kubectl get all -n kure-system -o yaml > kure-diagnostics.yaml
kubectl logs   -n kure-system -l app=kure-backend --all-containers >> kure-diagnostics.yaml
kubectl logs   -n kure-system -l app=kure-agent   --all-containers >> kure-diagnostics.yaml
kubectl describe pods -n kure-system >> kure-diagnostics.yaml
```

## Still stuck?

[Open an issue on GitHub](https://github.com/igor-koricanac/kure-monitor/issues) with the diagnostics bundle.
