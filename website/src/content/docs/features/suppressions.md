---
title: Suppressions
description: How to mute noisy alerts and ignore specific Security Scanner findings.
---

In large clusters, not every security finding is actionable. Some legacy workloads may intentionally violate best practices, and you don't want those warnings polluting your dashboard or triggering chat notifications.

Kure Monitor allows you to manage these exceptions via the **Suppressions** page in the **Admin Panel**.

## How Suppressions Work

When you suppress a rule or a pod, Kure Monitor completely silences alerts for it, keeping your main dashboard clean and focused.

### Ignoring Pods from the Dashboard

If a pod is failing (CrashLoopBackOff, ImagePullBackOff, etc.) and you want to mute it:
1. Go to the **Pod Monitoring** tab.
2. Find the noisy pod.
3. Click the **Ignore** button on the pod's card.
4. The pod is instantly moved to the **Ignored** tab and will no longer trigger chat notifications.

### Suppressing Security Findings

You cannot ignore Security findings directly from their dashboards. Because these findings represent architectural or security violations, exceptions are managed globally in the **Admin Panel → Suppressions**.

Here you can create rules to:
- **Exclude specific rules**: Completely silence a noisy rule (e.g. "Missing CPU Limits") across the cluster.
- **Exclude specific namespaces**: Ignore all warnings for a legacy namespace.
- **Exclude specific pods**: Ignore a specific workload that intentionally violates best practices.
- **Trusted Registries**: Specifically for the security scanner, add domains to a trusted registry list to suppress "Untrusted Image Registry" warnings for your private image hosts.
