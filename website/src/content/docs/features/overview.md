---
title: Features Overview
description: A tour of every feature in Kure Monitor — pod monitoring, security scanning, topology diagram, mirror pod testing, and more.
---

Kure Monitor's dashboard is organized into tabs. Each tab is documented in detail below.

All four features can be individually enabled or disabled at install time via the `features.*` Helm values — see [Helm Values → Feature toggles](/kure-monitor/configuration/helm-values/#feature-toggles). Disabling a feature hides its tab and, for Pod Monitoring and Security Scanning, also skips deploying the corresponding workloads and RBAC.

| Feature | What it does |
|---------|--------------|
| [Pod Monitoring](/kure-monitor/features/pod-monitoring/) | Real-time failure detection (CrashLoopBackOff, ImagePullBackOff, OOMKilled, Pending, FailedScheduling, FailedMount) with AI-generated solutions and live logs |
| [Security Scanner](/kure-monitor/features/security-scanner/) | 50+ misconfiguration checks with AI remediation, trusted-registry suppressions, and CSV/JSON/PDF export |
| [Topology Diagram](/kure-monitor/features/diagram/) | Interactive Kubernetes graph (per-namespace and per-workload), click nodes for manifests, click edges to focus paths |
| [Mirror Pod Testing](/kure-monitor/features/mirror-pod/) | Deploy a temporary copy of a failing pod with the AI fix applied — verify before committing to git |
| [Notifications](/kure-monitor/features/notifications/) | Slack and Microsoft Teams webhooks for new failures and critical findings |

## Cross-cutting

### Real-time updates

All data updates in real-time via WebSocket. No manual refresh, no polling.

### Dark mode

Toggle the sun/moon icon in the header. Dark theme is fully wired across status badges, modals, settings, and the manifest viewer.

### Pod lifecycle states

Pods cycle through:

| State | Meaning |
|-------|---------|
| **Active** | Currently failing, needs attention |
| **Investigating** | Someone is working on it |
| **Resolved** | Fixed; moved to history |
| **Ignored** | Intentionally hidden |

Configure auto-cleanup of resolved and ignored pods from **Admin → Settings → History Retention**.

### Authentication

User accounts (`read` / `write` / `admin`) for the dashboard; a separate shared `SERVICE_TOKEN` for agent and scanner traffic. See [Authentication](/kure-monitor/configuration/authentication/) for the full model.
