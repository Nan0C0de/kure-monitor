---
title: How to Fix Kubernetes OOMKilled (Exit Code 137) Errors
description: Complete guide to troubleshooting Kubernetes OOMKilled containers and Exit Code 137. Learn how to inspect cgroup memory limits, profile leaks, and configure memory requests.
---

`OOMKilled` (Out Of Memory Killed) is a Kubernetes error indicating that a container was terminated by the Linux kernel because it consumed more memory than its configured Kubernetes `limit`.

When a container hits its memory limit, it is instantly killed without warning. This often results in dropped connections and data corruption.

## What causes OOMKilled?

Unlike CPU limits (which throttle the container), memory limits are strictly enforced. Common causes include:
1. **Memory Leaks**: The application has a memory leak and slowly consumes RAM until it hits the limit.
2. **Spiky Workloads**: A sudden surge in traffic or a large file upload causes a temporary spike in memory usage that exceeds the limit.
3. **Java Heap Sizing**: The JVM heap size (`-Xmx`) is not configured correctly, or is set higher than the Kubernetes container memory limit. The JVM thinks it has more memory available than Kubernetes allows.
4. **Missing Requests/Limits**: If you don't set a memory request, the container might be scheduled on a node that doesn't have enough physical RAM available.

## How to debug manually

When a pod is `OOMKilled`, you will rarely see an error in the application logs, because the kernel kills the process abruptly.

**1. Verify the OOMKilled state**
Run a describe on the pod:
```bash
kubectl describe pod <pod-name> -n <namespace>
```
Look under the `Containers:` section for the `Last State:`. You will see `Reason: OOMKilled` and `Exit Code: 137`.

**2. Check the configured limits**
Check the `Limits:` section in the same describe output. If the limit is too low for your workload's baseline needs, you must increase it.

**3. Check Historical Metrics**
If you have Prometheus or Metrics Server installed, check the memory usage graph leading up to the crash. Was it a slow leak over days, or a sudden vertical spike?

## How to prevent OOMKilled with Kure Monitor

Reacting to `OOMKilled` means your application has already crashed. Kure Monitor helps you catch memory issues *before* they cause downtime.

**1. Proactive AI Advice Engine**
Kure Monitor's built-in **AI Advice** engine continuously scans your cluster. It detects containers that are missing memory limits, or containers where the memory limit is set dangerously close to the memory request (leading to highly volatile eviction risks).

**2. Instant AI Troubleshooting**
If a pod does get `OOMKilled`, Kure Monitor's Pod Monitoring dashboard detects it instantly. The AI will analyze the pod's manifest, flag the exact memory limit that was breached, and suggest the appropriate YAML modification to fix the capacity issue.

Stop fighting memory limits in the dark. [Install Kure Monitor](/getting-started/installation/) today.
