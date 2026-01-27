# Kure Pod Failure Test Cases

This directory contains 10 different pod failure scenarios to test the Kure monitoring system's ability to detect and report various types of pod failures.

## Test Cases

### 1. Image Pull BackOff (`01-image-pull-backoff.yaml`)
**Failure Type**: ImagePullBackOff  
**Cause**: Pod tries to pull a non-existent container image  
**Expected Status**: ImagePullBackOff or ErrImagePull

### 2. Secret Mount Failure (`02-secret-mount-failure.yaml`)
**Failure Type**: FailedMount  
**Cause**: Pod references a secret that doesn't exist  
**Expected Status**: FailedMount or Pending

### 3. ConfigMap Mount Failure (`03-configmap-mount-failure.yaml`)
**Failure Type**: FailedMount  
**Cause**: Pod references a ConfigMap that doesn't exist  
**Expected Status**: FailedMount or Pending

### 4. PVC Mount Failure (`04-pvc-mount-failure.yaml`)
**Failure Type**: FailedMount  
**Cause**: Pod references a PersistentVolumeClaim that doesn't exist  
**Expected Status**: FailedMount or Pending

### 5. Resource Limits Exceeded (`05-resource-limits-exceeded.yaml`)
**Failure Type**: FailedScheduling  
**Cause**: Pod requests more resources than available in cluster  
**Expected Status**: FailedScheduling or Pending

### 6. Node Selector No Match (`06-node-selector-no-match.yaml`)
**Failure Type**: FailedScheduling  
**Cause**: No nodes match the pod's nodeSelector requirements  
**Expected Status**: FailedScheduling or Pending

### 7. Crash Loop BackOff (`07-crash-loop-backoff.yaml`)
**Failure Type**: CrashLoopBackOff  
**Cause**: Container starts but immediately exits with error  
**Expected Status**: CrashLoopBackOff

### 8. Invalid Image Name (`08-invalid-image-name.yaml`)
**Failure Type**: InvalidImageName or ErrImagePull  
**Cause**: Malformed container image name  
**Expected Status**: InvalidImageName or ErrImagePull

### 9. Service Account Not Found (`09-service-account-not-found.yaml`)
**Failure Type**: FailedMount or CreateContainerConfigError  
**Cause**: Pod references a non-existent service account  
**Expected Status**: May vary by Kubernetes version

### 10. Init Container Failure (`10-init-container-failure.yaml`)
**Failure Type**: Init:Error or Init:CrashLoopBackOff  
**Cause**: Init container fails, preventing main container from starting  
**Expected Status**: Init containers appear in container status

## Usage

### Apply Individual Test Cases
```bash
# Apply a specific test case
kubectl apply -f examples/01-image-pull-backoff.yaml

# Check the pod status
kubectl get pods

# View detailed information
kubectl describe pod failed-pod-image-pull
```

### Apply All Test Cases
```bash
# Apply all test cases at once
kubectl apply -f examples/

# Wait a few minutes for failures to manifest
sleep 180

# Check all failing pods
kubectl get pods --field-selector=status.phase!=Running,status.phase!=Succeeded
```

### Clean Up Test Cases
```bash
# Remove all test pods
kubectl delete -f examples/

# Or remove individually
kubectl delete pod failed-pod-image-pull
```

## Verification

After applying these test cases, the Kure monitoring system should detect and report each failure with:

1. **Proper failure reason** (ImagePullBackOff, FailedMount, etc.)
2. **Detailed failure message** (specific error details)
3. **AI-generated solution** (troubleshooting steps)
4. **Pod events** (Kubernetes events leading to failure)
5. **Container statuses** (current container states)

## Testing the Frontend

1. Apply several test cases
2. Access the Kure frontend dashboard
3. Verify that failed pods appear with:
   - ✅ Red transparent background on status badges
   - ✅ Bold pod names
   - ✅ Proper alignment
   - ✅ Clickable pod names, status, and dates to expand details
   - ✅ Detailed error messages and solutions

## Notes

- Some failures may take a few minutes to manifest
- Resource-based failures (test case #5) may not trigger on small clusters
- Node selector failures (test case #6) depend on your cluster's node labels
- Init container failures (test case #10) show different status formats

---

## Security Scan Test Cases

The `security-scan-tests.yaml` file contains test resources to verify the security scanner detects various security issues.

### Security Test Cases

| Test | Resource | Security Issue |
|------|----------|----------------|
| Namespace without PSA | `test-security-scan` namespace | Missing Pod Security Admission labels |
| Namespace with privileged PSA | `test-privileged-ns` namespace | PSA enforce set to 'privileged' |
| Ingress without TLS | `insecure-ingress-no-tls` | Traffic will be unencrypted |
| Ingress with wildcard host | `insecure-ingress-wildcard` | Exposes services to unintended subdomains |
| Ingress with dangerous annotation | `insecure-ingress-snippet` | Configuration snippet injection risk |
| Pod without seccomp | `pod-no-seccomp` | Missing seccomp profile (PSS Restricted) |
| ClusterRoleBinding to anonymous | `insecure-anonymous-binding` | Grants permissions to unauthenticated users |
| ServiceAccount with cluster-admin | `insecure-sa-cluster-admin` | Overprivileged ServiceAccount |
| HA Deployment without PDB | `ha-deployment-no-pdb` | No availability guarantee during disruptions |
| ConfigMap with secrets | `insecure-config` | Sensitive data in ConfigMap (passwords, API keys) |
| ConfigMap with sensitive keys | `sensitive-keys-config` | Key names suggest sensitive data |
| CronJob privileged | `insecure-cronjob-privileged` | Privileged container in scheduled job |
| CronJob host network | `insecure-cronjob-hostnet` | Host network access in scheduled job |
| CronJob excessive history | `cronjob-excessive-history` | Retains too many completed jobs |
| Missing ResourceQuota | `test-security-scan` namespace | No resource limits on namespace |
| Missing LimitRange | `test-security-scan` namespace | No default container limits |

### Usage

```bash
# Apply security test cases
kubectl apply -f examples/security-scan-tests.yaml

# Check the security scanner findings in the Kure dashboard
# Or check the backend API directly:
curl http://localhost:8000/api/security/findings

# Clean up
kubectl delete -f examples/security-scan-tests.yaml
```

### Expected Security Findings

After applying the security test cases, the security scanner should detect:

1. **PSA Compliance** - Namespaces without PSA labels or with 'privileged' enforce
2. **Ingress Security** - Missing TLS, wildcard hosts, dangerous annotations
3. **Container Security** - Missing seccomp profiles
4. **RBAC Issues** - Anonymous bindings, overprivileged ServiceAccounts
5. **Availability** - HA deployments without PodDisruptionBudgets
6. **Resource Management** - Namespaces without ResourceQuota/LimitRange
7. **Secret Exposure** - Sensitive data patterns in ConfigMaps
8. **Job Security** - Privileged or host-networked CronJobs

### Comparison Resources

The file also includes "secure" versions of some resources for comparison:
- `pod-with-seccomp` - Properly configured pod with seccomp profile
- `ha-deployment-with-pdb` - HA deployment with PodDisruptionBudget

These should NOT trigger security findings and demonstrate best practices.