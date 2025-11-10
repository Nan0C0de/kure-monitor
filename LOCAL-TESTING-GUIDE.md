# Local Testing Guide with Kind

This guide provides a complete workflow for testing Kure locally before publishing.

## Prerequisites

- Docker installed and running
- Kind cluster running
- kubectl configured

## Quick Start (Automated)

```bash
# 1. Run the automated test script
cd k8s
./test-local.sh [your-cluster-name]

# Default cluster name is 'kure' if not specified
./test-local.sh kure
```

The script will:
1. Build all Docker images locally
2. Load images into Kind cluster
3. Deploy all components
4. Wait for pods to be ready
5. Show access instructions

## Manual Testing Steps

If you prefer to test manually or need to troubleshoot:

### 1. Build Images

```bash
cd backend && docker build -t kure-backend:local .
cd ../frontend && docker build -t kure-frontend:local .
cd ../agent && docker build -t kure-agent:local .
cd ../security-scanner && docker build -t kure-security-scanner:local .
cd ..
```

### 2. Load Images into Kind

```bash
kind load docker-image kure-backend:local --name kure
kind load docker-image kure-frontend:local --name kure
kind load docker-image kure-agent:local --name kure
kind load docker-image kure-security-scanner:local --name kure
```

### 3. Deploy to Kind

```bash
cd k8s

# Deploy core components
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f rbac.yaml
kubectl apply -f postgresql.yaml
kubectl apply -f backend.yaml
kubectl apply -f frontend.yaml

# Deploy agents
kubectl apply -f agent.yaml
kubectl apply -f security-scanner.yaml
```

### 4. Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n kure-system

# Expected output:
# NAME                                       READY   STATUS    RESTARTS   AGE
# kure-agent-xxxxx                           1/1     Running   0          1m
# kure-backend-xxxxxxxxxx-xxxxx              1/1     Running   0          2m
# kure-frontend-xxxxxxxxxx-xxxxx             1/1     Running   0          2m
# kure-postgresql-xxxxxxxxxx-xxxxx           1/1     Running   0          2m
# kure-security-scanner-xxxxxxxxxx-xxxxx     1/1     Running   0          1m
```

## Testing Scenarios

### Test 1: Verify Basic Connectivity

```bash
# Port forward the frontend
kubectl port-forward -n kure-system svc/kure-frontend 3000:8080

# Open browser: http://localhost:3000
# You should see the Kure dashboard with two tabs:
# - Pod Monitoring
# - Security Scan
```

### Test 2: Test Security Scanner

```bash
# Deploy pods with security issues
kubectl apply -f test-insecure-pod.yaml

# This creates:
# - Privileged container (HIGH severity)
# - Container running as root (MEDIUM severity)
# - Missing resource limits (MEDIUM severity)
# - Host network enabled (HIGH severity)
# - Host PID enabled (HIGH severity)
# - LoadBalancer service (MEDIUM severity)
# - ClusterRole with wildcard permissions (HIGH severity)
```

Wait 2 minutes for the scan to run, then check:

```bash
# View security scanner logs
kubectl logs -n kure-system -l app=kure-security-scanner -f

# You should see:
# - "Starting new security scan..."
# - "Scanning pods for security issues..."
# - "Sending security finding for Pod/test-security/insecure-nginx..."
# - Multiple findings being reported
```

Verify in the frontend:
1. Go to **Security Scan** tab
2. You should see multiple findings
3. Click on a finding to see details
4. Click the **X** button to dismiss a finding

### Test 3: Test Pod Monitoring

```bash
# Create a failing pod
kubectl run failing-pod --image=nonexistent:latest --namespace=test-security

# Wait ~30 seconds, then check Pod Monitoring tab
# You should see the failing pod with ImagePullBackOff
```

### Test 4: Test Real-time Updates

1. Keep the frontend open
2. Deploy new insecure resources:
   ```bash
   kubectl run test-privileged --image=nginx --privileged=true -n test-security
   ```
3. Wait for next scan cycle (~2 minutes)
4. New findings should appear automatically without refresh

### Test 5: Test WebSocket Connection

1. Open browser DevTools (F12)
2. Go to Network tab → WS (WebSocket)
3. You should see an active WebSocket connection
4. When findings are reported, you'll see messages like:
   ```json
   {
     "type": "security_finding",
     "data": { ... }
   }
   ```

### Test 6: Test Backend API

```bash
# Port forward backend
kubectl port-forward -n kure-system svc/kure-backend 8000:8000

# Test endpoints
curl http://localhost:8000/api/security/findings | jq
curl http://localhost:8000/api/pods/failed | jq
curl http://localhost:8000/api/cluster/info | jq

# Test dismissing a finding (replace ID)
curl -X DELETE http://localhost:8000/api/security/findings/1

# Clear all findings
curl -X POST http://localhost:8000/api/security/scan/clear
```

### Test 7: Test Database Persistence

```bash
# Check PostgreSQL database
kubectl exec -n kure-system deployment/kure-postgresql -- psql -U kure -d kure -c "SELECT COUNT(*) FROM security_findings;"
kubectl exec -n kure-system deployment/kure-postgresql -- psql -U kure -d kure -c "SELECT resource_type, severity, title FROM security_findings LIMIT 10;"

# Restart security scanner and verify findings persist
kubectl rollout restart deployment/kure-security-scanner -n kure-system
kubectl rollout status deployment/kure-security-scanner -n kure-system

# Findings should still be in the frontend
```

### Test 8: Test Conditional Deployment

```bash
# Test deploying only security scanner
./cleanup.sh
./test-local.sh --security-scanner-only

# Verify only security scanner is running
kubectl get deployments -n kure-system

# Test deploying only pod monitor
./cleanup.sh
./test-local.sh --pod-monitor-only

# Verify only agent is running
kubectl get deployments -n kure-system
```

## Viewing Logs

```bash
# All pods
kubectl logs -n kure-system --all-containers=true -f

# Specific components
kubectl logs -n kure-system -l app=kure-backend -f
kubectl logs -n kure-system -l app=kure-agent -f
kubectl logs -n kure-system -l app=kure-security-scanner -f
kubectl logs -n kure-system -l app=kure-frontend -f
```

## Common Issues & Solutions

### Issue: Images not found in Kind

**Solution:**
```bash
# List images in Kind
docker exec -it kure-control-plane crictl images | grep kure

# If missing, reload:
kind load docker-image kure-security-scanner:local --name kure
```

### Issue: Security scanner not finding resources

**Solution:**
```bash
# Check RBAC permissions
kubectl auth can-i list pods --as=system:serviceaccount:kure-system:kure-security-scanner
kubectl auth can-i list clusterroles --as=system:serviceaccount:kure-system:kure-security-scanner

# If false, reapply RBAC:
kubectl apply -f k8s/rbac.yaml
kubectl rollout restart deployment/kure-security-scanner -n kure-system
```

### Issue: Frontend not loading

**Solution:**
```bash
# Check frontend logs
kubectl logs -n kure-system -l app=kure-frontend

# Check if backend is accessible from frontend
kubectl exec -n kure-system deployment/kure-frontend -- wget -O- http://kure-backend:8000/api/cluster/info
```

### Issue: WebSocket connection failing

**Solution:**
```bash
# Check backend logs for WebSocket errors
kubectl logs -n kure-system -l app=kure-backend | grep -i websocket

# Verify backend service
kubectl get svc kure-backend -n kure-system
```

### Issue: Database connection errors

**Solution:**
```bash
# Check PostgreSQL is running
kubectl get pods -n kure-system -l app=kure-postgresql

# Check database environment variables
kubectl exec -n kure-system deployment/kure-backend -- env | grep DATABASE

# Test connection from backend
kubectl exec -n kure-system deployment/kure-backend -- python -c "
import asyncpg
import asyncio
async def test():
    conn = await asyncpg.connect('postgresql://kure:kure-password-change-me@kure-postgresql:5432/kure')
    print('Connected!')
asyncio.run(test())
"
```

## Performance Testing

Monitor resource usage:

```bash
# Watch resource consumption
kubectl top pods -n kure-system

# Expected ranges:
# Backend:           50-200 MB RAM, 10-100m CPU
# Frontend:          20-100 MB RAM, 5-50m CPU
# Agent:             30-100 MB RAM, 10-50m CPU
# Security Scanner:  50-200 MB RAM, 20-100m CPU
# PostgreSQL:        50-500 MB RAM, 10-200m CPU
```

## Cleanup

```bash
# Quick cleanup
cd k8s
./cleanup.sh

# Or manual cleanup
kubectl delete namespace kure-system
kubectl delete -f test-insecure-pod.yaml
kubectl delete clusterrole kure-agent kure-security-scanner wildcard-permissions
kubectl delete clusterrolebinding kure-agent kure-security-scanner
```

## Pre-Production Checklist

Before pushing images and deploying to production:

- [ ] All pods start successfully
- [ ] Security scanner detects test issues
- [ ] Pod monitor detects failing pods
- [ ] Frontend displays both tabs correctly
- [ ] WebSocket updates work in real-time
- [ ] Findings can be dismissed
- [ ] Database persists data after restarts
- [ ] API endpoints respond correctly
- [ ] No error logs in any component
- [ ] Resource usage is acceptable
- [ ] RBAC permissions are minimal and correct
- [ ] Images are tagged with proper version (not :local)

## Next Steps

Once testing is complete:

1. **Tag and Push Images:**
   ```bash
   docker tag kure-backend:local ghcr.io/nan0c0de/kure-monitor/backend:1.0.0
   docker tag kure-frontend:local ghcr.io/nan0c0de/kure-monitor/frontend:1.0.0
   docker tag kure-agent:local ghcr.io/nan0c0de/kure-monitor/agent:1.0.0
   docker tag kure-security-scanner:local ghcr.io/nan0c0de/kure-monitor/security-scanner:1.0.0

   docker push ghcr.io/nan0c0de/kure-monitor/backend:1.0.0
   docker push ghcr.io/nan0c0de/kure-monitor/frontend:1.0.0
   docker push ghcr.io/nan0c0de/kure-monitor/agent:1.0.0
   docker push ghcr.io/nan0c0de/kure-monitor/security-scanner:1.0.0
   ```

2. **Update Helm Chart:**
   - Update version in `helm/Chart.yaml`
   - Update image tags in `helm/values.yaml`
   - Test Helm installation

3. **Update Documentation:**
   - Update README.md with new features
   - Document security scanner configuration
   - Update installation instructions

4. **Create Release:**
   - Tag the git repository
   - Create GitHub release
   - Update Artifact Hub metadata