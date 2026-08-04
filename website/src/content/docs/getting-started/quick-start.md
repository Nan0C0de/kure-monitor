---
title: Quick Start
description: TL;DR — install Kure Monitor with Helm, log in, configure an LLM, and start diagnosing pod failures.
---

Five minutes from zero to a working dashboard.

## 1. Install the chart

```bash
helm repo add kure-monitor https://kuremonitor.com/
helm repo update

helm install kure-monitor kure-monitor/kure \
  --namespace kure-system \
  --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)"
```

## 2. Open the dashboard

```bash
kubectl port-forward svc/kure-monitor-frontend 8080:8080 -n kure-system
```

Visit <http://localhost:8080>. On the very first visit, the dashboard prompts you to create the initial **admin** account.

## 3. Configure an LLM provider

In the Admin panel:

1. **AI Configuration** → pick a provider
2. Enter your API key
3. Pick a model
4. **Test Connection** → **Save**

For air-gapped clusters, point at an in-cluster Ollama and Kure data never leaves your network. See [LLM Providers](/configuration/llm-providers/).

## 4. Watch a failure roll in

In another terminal:

```bash
# trigger a CrashLoopBackOff
kubectl run crash-test --image=busybox --restart=Never -- sh -c 'exit 1'
```

Within a few seconds the dashboard shows the failure with an AI-generated explanation, the pod manifest, recent events, and last container logs. Click **Test Fix** to deploy a [mirror pod](/features/mirror-pod/) with the AI-suggested fix applied.

## 5. Trigger a security scan

Open the **Security** tab. The scanner audits all pods on a schedule and on demand. Click any finding for severity, affected resource, and an AI-generated remediation.

## What's next

- [Features overview](/features/overview/) — every tab and what it does
- [Configuration overview](/configuration/overview/) — Helm values, env vars, retention
- [Authentication](/configuration/authentication/) — how user accounts and the service token work
- [Troubleshooting](/reference/troubleshooting/) — when things don't go to plan
