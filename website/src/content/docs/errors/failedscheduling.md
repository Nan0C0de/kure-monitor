---
title: "FailedScheduling in Kubernetes: Causes, Debugging & Fixes"
description: Complete troubleshooting guide for Kubernetes FailedScheduling and Pod Pending errors. Learn how to debug insufficient CPU/memory, node affinity, taints, and tolerations.
---

`FailedScheduling` is a Kubernetes event that occurs when the `kube-scheduler` cannot find any worker node in the cluster that satisfies all the placement constraints of a requested Pod.

When a pod triggers `FailedScheduling`, it remains stuck in the `Pending` state indefinitely until cluster resources change or scheduling constraints are relaxed.

---

## What Causes FailedScheduling?

The Kubernetes scheduler evaluates every node through filtering and scoring stages. Common reasons pods fail scheduling include:

1. **`0/N nodes are available: insufficient cpu / memory`**: Requested resources (`resources.requests`) exceed the unallocated capacity of every worker node.
2. **`node(s) had untolerated taint`**: Worker nodes have taints (such as `node.kubernetes.io/unreachable`, spot instance tags, or GPU flags) that the pod manifest does not tolerate.
3. **`node(s) didn't match Pod's node selector / affinity`**: `nodeSelector`, `nodeAffinity`, or `podAntiAffinity` rules cannot be satisfied.
4. **`0/N nodes available: node(s) had volume node affinity conflict`**: A PersistentVolume (PV) is bound to a specific availability zone or node, but the scheduler cannot place the pod in that zone.
5. **`max node pod limit reached`**: The node has reached its maximum configured pod density (default 110 pods per node).

---

## How to Debug FailedScheduling Manually

Because the pod has never started on a node, **there are no container logs**. All diagnostic information is in the Kubernetes events.

### Step 1: Inspect Pod Events
Run `kubectl describe` to see the exact scheduling rejection reason:

```bash
kubectl describe pod <pod-name> -n <namespace>
```

Scroll to the **Events** table at the bottom. You will see events similar to:

```text
Events:
  Type     Reason            Age   From               Message
  ----     ------            ----  ----               -------
  Warning  FailedScheduling  42s   default-scheduler  0/6 nodes are available: 3 Insufficient memory, 3 node(s) had untolerated taint {node-role.kubernetes.io/master: }.
```

### Step 2: Check Node Resource Allocatable vs. Requests
Check the cluster-wide resource allocation to see which nodes are saturated:

```bash
kubectl describe nodes | grep -A 8 "Allocated resources:"
```

### Step 3: Inspect Taints and Labels on Nodes
If resource capacity is sufficient, check node taints:

```bash
kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints
```

---

## How to Fix FailedScheduling

| Root Cause | Immediate Remediation |
|---|---|
| **Insufficient CPU / Memory** | Lower excessive `resources.requests` in the pod spec, or scale up your worker node pool / enable Cluster Autoscaler. |
| **Untolerated Taints** | Add the matching `tolerations` block to the pod manifest: <br/> `tolerations:` <br/> `- key: "gpu" operator: "Equal" value: "true" effect: "NoSchedule"` |
| **Node Affinity Conflict** | Relax `requiredDuringSchedulingIgnoredDuringExecution` to `preferredDuringSchedulingIgnoredDuringExecution`. |
| **Zone PV Affinity** | Ensure the pod's node affinity matches the availability zone of the attached EBS/GCP persistent disk. |

---

## Automate FailedScheduling Triage with Kure Monitor

Instead of manually parsing complex multi-node scheduler strings across dozens of pending pods:

1. **Instant Pending Pod Detection:** Kure Monitor watches the cluster state and automatically flags pods stuck in `Pending` past their grace period.
2. **Contextual Root-Cause Analysis:** Kure's AI Advice engine cross-references node capacities, active taints, and the pod's resource requests.
3. **Exact Remediation:** Kure generates the exact YAML patch (lowered requests, missing tolerations, or relaxed affinity) and lets you test it safely before committing.

[Install Kure Monitor](/getting-started/installation/) to automate Kubernetes troubleshooting.
