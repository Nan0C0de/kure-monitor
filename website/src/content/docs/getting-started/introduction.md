---
title: Introduction
description: What Kure Monitor is, what it does, and how it fits next to your existing observability stack.
---

Kure Monitor is a Kubernetes health monitoring tool that helps you understand **why** your workloads fail. When a pod crashes, gets stuck pending, or can't pull an image, Kure detects it instantly and provides AI-generated troubleshooting guidance to help you fix it fast. It also continuously scans your cluster for security misconfigurations and gives you a real-time overview of cluster topology — all from a single dashboard.

## What's in the box

| Capability | Description |
|------------|-------------|
| **AI-Powered Troubleshooting** | Contextual fixes from pod events, logs, and manifest analysis using OpenAI, Anthropic, Groq, Google Gemini, GitHub Copilot, or Ollama |
| **Real-time Failure Detection** | CrashLoopBackOff, ImagePullBackOff, Pending, OOMKilled, FailedScheduling, FailedMount |
| **Security Scanning** | 50+ checks: privileged containers, host namespaces, dangerous capabilities, missing seccomp/AppArmor, root containers, RBAC misconfigs, untrusted registries, missing limits |
| **Topology Diagram** | Interactive Kubernetes graph (per-namespace and per-workload), click nodes for manifests, click edges to focus paths |
| **Mirror Pod Testing** | Deploy a temporary copy of a failing pod with the AI-suggested fix applied to verify before committing |
| **Live Pod Logs** | Stream logs in real-time with container selection |
| **Export Findings** | Security findings to CSV, JSON, and PDF |
| **Notifications** | Slack and Microsoft Teams webhooks |
| **Auth** | User accounts with read/write/admin roles, HttpOnly session cookies, rate-limited login |
| **Prometheus Metrics** | `/metrics` endpoint with optional ServiceMonitor support |

## Limitations

Kure is focused on failure diagnosis, not general observability:

- **No Prometheus dependency** — Kure works standalone
- **Not a metrics platform** — no time-series, no alerting rules, no historical dashboards
- **Not a log aggregator** — logs are fetched on-demand, not stored or indexed
- **Single cluster only** — monitors one Kubernetes cluster per installation

Kure complements your existing observability stack — it doesn't replace it.

## Architecture overview

```
                         Kubernetes Cluster
  ┌────────────────────────────────────────────────────────────────┐
  │                                                                │
  │   ┌──────────────┐     ┌──────────────────┐     ┌───────────┐  │
  │   │    Agent     │────>│                  │<────│ Frontend  │  │
  │   │ (DaemonSet)  │ HTTP│     Backend      │ WS  │  (React)  │  │
  │   └──────┬───────┘     │    (FastAPI)     │     └───────────┘  │
  │          │             │                  │                    │
  │   ┌──────┴───────┐     │                  │                    │
  │   │   Security   │────>│                  │                    │
  │   │   Scanner    │ HTTP└────────┬─────────┘                    │
  │   └──────┬───────┘              │                              │
  │          │                      │                              │
  │          │              ┌───────┴──────┐                       │
  │    K8s API Server       │  PostgreSQL  │                       │
  │   (watch pods,          │   Database   │                       │
  │    events, nodes)       └──────────────┘                       │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │   LLM Provider   │
                          │ OpenAI/Anthropic │
                          │ Groq/Gemini/     │
                          │ Copilot/Ollama   │
                          └──────────────────┘
```

See [Architecture](/kure-monitor/reference/architecture/) for the full breakdown.

## Next steps

- [Installation](/kure-monitor/getting-started/installation/) — full install guide
- [Quick Start](/kure-monitor/getting-started/quick-start/) — TL;DR for impatient operators
- [Features](/kure-monitor/features/overview/) — what each tab does
- [Configuration](/kure-monitor/configuration/overview/) — Helm values, LLM providers, auth
