# Testing the Security Scanner Feature

This guide explains how to test the new security scanner functionality locally.

## Prerequisites

- Docker installed
- Kubernetes cluster (kind, minikube, or other)
- kubectl configured
- Existing Kure deployment (backend, frontend, PostgreSQL)

## Step 1: Build the Security Scanner Image

Build the Docker image locally:

```bash
cd security-scanner
docker build -t kure-security-scanner:latest .
cd ..
```

## Step 2: Load Image into Kubernetes

If using **kind**:
```bash
kind load docker-image kure-security-scanner:latest --name <your-cluster-name>
```

If using **minikube**:
```bash
minikube image load kure-security-scanner:latest
```

## Step 3: Deploy the Security Scanner

### Option A: Deploy Everything (Both Agents)
```bash
# Apply RBAC first (updated with security scanner permissions)
kubectl apply -f k8s/rbac.yaml

# Deploy the security scanner
kubectl apply -f k8s/security-scanner.yaml

# Or use the deploy script
./k8s/deploy.sh
```

### Option B: Deploy Only Security Scanner
```bash
./k8s/deploy.sh --security-scanner-only
```

### Option C: Deploy Only Pod Monitor
```bash
./k8s/deploy.sh --pod-monitor-only
```

## Step 4: Verify Deployment

Check if the security scanner pod is running:

```bash
kubectl get pods -n kure-system -l app=kure-security-scanner
```

Expected output:
```
NAME                                      READY   STATUS    RESTARTS   AGE
kure-security-scanner-xxxxxxxxxx-xxxxx    1/1     Running   0          30s
```

Check logs to see if it's scanning:

```bash
kubectl logs -n kure-system -l app=kure-security-scanner -f
```

Expected log output:
```
2025-11-10 12:00:00 - __main__ - INFO - Starting security scanner (scan interval: 300s)
2025-11-10 12:00:00 - __main__ - INFO - Backend URL: http://kure-backend:8000
2025-11-10 12:00:00 - services.security_scanner - INFO - Using local kubeconfig
2025-11-10 12:00:00 - services.security_scanner - INFO - Starting new security scan...
2025-11-10 12:00:00 - services.backend_client - INFO - Clearing previous security findings from backend
2025-11-10 12:00:01 - services.security_scanner - INFO - Scanning pods for security issues...
```

## Step 5: Test the Frontend

1. Access the Kure dashboard (default: http://localhost:30080 or http://kure.local)
2. You should see **two tabs**:
   - **Pod Monitoring** - Shows pod failures
   - **Security Scan** - Shows security findings

3. Click on the **Security Scan** tab
4. You should see security issues detected in your cluster

## Step 6: Verify Backend API

Test the API endpoints directly:

```bash
# Get security findings
kubectl exec -n kure-system deployment/kure-backend -- curl http://localhost:8000/api/security/findings

# Check PostgreSQL database
kubectl exec -n kure-system deployment/kure-postgresql -- psql -U kure -d kure -c "SELECT * FROM security_findings;"
```

## Step 7: Create Test Security Issues

To generate security findings for testing, deploy a pod with security issues:

```bash
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: insecure-pod
  namespace: default
spec:
  containers:
  - name: nginx
    image: nginx
    securityContext:
      privileged: true
      runAsUser: 0
    resources: {}  # No resource limits
  hostNetwork: true
  hostPID: true
EOF
```

This pod will trigger multiple security findings:
- Privileged container
- Running as root
- Missing resource limits
- Using host network
- Using host PID namespace

Wait for the next scan cycle (default: 5 minutes), or check logs to see findings being reported.

## Step 8: Test Finding Dismissal

1. In the frontend, click on a security finding to expand details
2. Click the **X** button to dismiss the finding
3. The finding should disappear from the list
4. Verify in logs that the dismiss API was called

## Step 9: Test WebSocket Updates

1. Keep the frontend open in your browser
2. Deploy a new insecure resource
3. Wait for the scan cycle
4. You should see new findings appear in real-time without refreshing

## Troubleshooting

### Security Scanner Pod Not Starting

Check pod events:
```bash
kubectl describe pod -n kure-system -l app=kure-security-scanner
```

Check logs for errors:
```bash
kubectl logs -n kure-system -l app=kure-security-scanner
```

### No Security Findings Appearing

1. Check scanner logs for errors
2. Verify RBAC permissions:
   ```bash
   kubectl auth can-i list pods --as=system:serviceaccount:kure-system:kure-security-scanner
   ```
3. Check backend logs:
   ```bash
   kubectl logs -n kure-system -l app=kure-backend
   ```
4. Verify database connection:
   ```bash
   kubectl exec -n kure-system deployment/kure-backend -- env | grep DATABASE
   ```

### Frontend Not Showing Security Tab

1. Check browser console for errors (F12)
2. Verify backend API is accessible:
   ```bash
   kubectl port-forward -n kure-system svc/kure-backend 8000:8000
   curl http://localhost:8000/api/security/findings
   ```
3. Check WebSocket connection in browser dev tools (Network tab → WS)

## Configuration Options

### Change Scan Interval

Edit the deployment:
```bash
kubectl edit deployment kure-security-scanner -n kure-system
```

Change the `SCAN_INTERVAL` environment variable (in seconds):
```yaml
env:
- name: SCAN_INTERVAL
  value: "600"  # 10 minutes
```

### Disable Security Scanner

```bash
kubectl delete deployment kure-security-scanner -n kure-system
```

Or scale to zero:
```bash
kubectl scale deployment kure-security-scanner -n kure-system --replicas=0
```

## Clean Up Test Resources

Remove the insecure test pod:
```bash
kubectl delete pod insecure-pod -n default
```

Clear all security findings:
```bash
curl -X POST http://localhost:8000/api/security/scan/clear
```

## Expected Behavior

- **First Scan**: Should take 30-60 seconds depending on cluster size
- **Scan Frequency**: Every 5 minutes by default (configurable via `SCAN_INTERVAL`)
- **Finding Display**: Real-time updates via WebSocket
- **Finding Persistence**: Stored in PostgreSQL database
- **Finding Deduplication**: Same finding (resource+title) is updated, not duplicated

## Next Steps

Once tested locally:
1. Push the image to your registry
2. Update the image tag in `k8s/security-scanner.yaml`
3. Update Helm chart if using Helm deployment
4. Deploy to production cluster