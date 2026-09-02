---
title: "Case Study: Running Local LLMs (Ollama) in Air-Gapped Kubernetes Without Data Leakage"
description: Architectural case study on deploying private, air-gapped Kubernetes AI observability with Ollama and Kure Monitor. No telemetry, no external egress.
---

**Published:** September 2, 2026 | **Author:** Kure Monitor Engineering Team | **Category:** Architecture & Security Case Studies

---

Many defense, healthcare, and financial institutions operate Kubernetes clusters in strictly **air-gapped** or highly regulated environments. 

While engineering teams in these organizations face the same complex distributed systems failures (`CrashLoopBackOff`, `OOMKilled`, cascading ingress timeouts), policy strictly prohibits streaming telemetry, pod logs, or cluster manifests to external cloud APIs like OpenAI or Anthropic.

In this case study, we explore the architectural design and implementation of running self-hosted, private AI observability in an air-gapped cluster using **Ollama** and **Kure Monitor**.

---

## The Challenge: Zero Egress & Zero Secret Access

When deploying AI-assisted operations in sensitive environments, three security constraints are mandatory:

1. **Zero Egress (Network Isolation):** The Kubernetes cluster has no route to the public internet. All container images and model weights must be sourced from an internal private registry.
2. **RBAC Least Privilege:** The AI engine must not have read access to Kubernetes `Secrets` or sensitive ConfigMaps.
3. **Deterministic Output:** AI suggestions must be actionable, reproducible, and verifiable before applying changes to production manifests.

```
                   Air-Gapped Kubernetes Cluster
  ┌─────────────────────────────────────────────────────────────┐
  │                                                             │
  │   ┌──────────────────┐           ┌──────────────────────┐   │
  │   │   Kure Monitor   │   HTTP    │     Ollama Pod       │   │
  │   │   (Backend)      │──────────>│  (Local Mistral /    │   │
  │   └────────┬─────────┘  (No WAN) │   DeepSeek / Llama)  │   │
  │            │                     └──────────────────────┘   │
  │            ▼                                                │
  │   ┌──────────────────┐                                      │
  │   │ Kubernetes API   │ (Read Pods, Events, Logs)            │
  │   │ (No Secret Read) │ (Intentionally No Secrets Access)    │
  │   └──────────────────┘                                      │
  │                                                             │
  └─────────────────────────────────────────────────────────────┘
```

---

## 1. Deploying Ollama with Pre-Loaded Weights

In an air-gapped cluster, models cannot be downloaded on-the-fly via `ollama pull`. Instead, the model weights (e.g., `mistral:7b-instruct` or `qwen2.5-coder:7b`) are baked into a PersistentVolume or bundled into an internal container image.

### Example Ollama Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama
  namespace: kure-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ollama
  template:
    metadata:
      labels:
        app: ollama
    spec:
      containers:
      - name: ollama
        image: internal-registry.corp/ai/ollama:latest
        ports:
        - containerPort: 11434
        resources:
          limits:
            memory: 16Gi
            cpu: "8"
        volumeMounts:
        - name: model-storage
          mountPath: /root/.ollama
      volumes:
      - name: model-storage
        persistentVolumeClaim:
          claimName: ollama-models-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: ollama
  namespace: kure-system
spec:
  ports:
  - port: 11434
    targetPort: 11434
  selector:
    app: ollama
```

---

## 2. Configuring Kure Monitor for Air-Gapped Operation

Kure Monitor is installed using Helm without needing API keys or provider flags at install time:

```bash
helm upgrade --install kure-monitor kure-monitor/kure \
  --namespace kure-system --create-namespace \
  --set postgresql.password="$(openssl rand -hex 24)"
```

### Auto-Detecting In-Cluster Models via UI
Once installed, log into the Kure Monitor dashboard as an admin:

1. Navigate to **Admin Panel → AI Configuration**.
2. Click **Auto-Detect Cluster LLMs** — Kure automatically scans the cluster for running Ollama, vLLM, or LocalAI services and discovers loaded models.
3. Select `http://ollama.kure-system.svc.cluster.local:11434` and your desired model (e.g., `mistral:7b-instruct` or `qwen2.5-coder:7b`).
4. Click **Test Connection** → **Save Configuration**.

Alternatively, you can configure it via the authenticated Admin REST API:

```bash
curl -X POST http://localhost:8080/api/admin/llm/config \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "custom",
    "base_url": "http://ollama.kure-system.svc.cluster.local:11434/v1",
    "model": "mistral:7b-instruct",
    "api_key": ""
  }'
```

### Security Proof: Restricted RBAC
Kure Monitor's Helm chart intentionally restricts the backend ServiceAccount. The cluster role excludes `secrets`:

```yaml
# kure-monitor ClusterRole snippet
rules:
- apiGroups: [""]
  resources: ["pods", "pods/log", "events", "nodes", "services", "namespaces"]
  verbs: ["get", "list", "watch"]
# Note: 'secrets' is intentionally omitted from resources.
```

Even if a malicious prompt injection occurs, the backend has no API token capability to query Kubernetes secret values.

---

## 3. Real Incident Walkthrough: Diagnosing a Silent DB Crash

In a test air-gapped namespace, a payment gateway pod entered `CrashLoopBackOff`:

1. **Instant Detection:** The Kure Monitor DaemonSet detected the container termination event in 300ms.
2. **Context Compilation:** The backend extracted:
   - Pod specification (excluding sensitive values)
   - Last 50 lines of `--previous` container logs
   - Kubernetes kubelet events (`BackOff`, `Unhealthy`)
3. **Local Inference:** Kure dispatched the contextual prompt to the local `http://ollama:11434` service inside the cluster.
4. **Resolution in 4 Seconds:** The local model identified that the database driver failed due to a missing TCP keepalive parameter in `application.yaml`, outputting the exact `kubectl patch` command.

---

## 4. Safe Verification via Mirror Pods

Before applying the fix to production manifests, the platform engineer used Kure Monitor's **Mirror Pod Testing** button.

Kure deployed an ephemeral mirror pod with the suggested config patch, confirmed that the container reached `Ready: 1/1` without restarting, and auto-deleted the test pod after 3 minutes.

---

## Key Results & Takeaways

| Metric | Cloud LLM (Baseline) | Air-Gapped Kure + Ollama |
|---|---|---|
| **Egress Bandwidth** | ~50MB/day | **0 KB (Fully isolated)** |
| **Data Privacy Compliance** | Requires third-party DPA | **100% On-Premise / Compliant** |
| **Mean Time to Diagnosis (MTTD)** | ~18 minutes (manual kubectl) | **< 15 seconds** |
| **External Dependency** | Requires public SaaS uptime | **Self-contained & resilient** |

Running AI-assisted Kubernetes troubleshooting does not require sacrificing data sovereignty or cluster isolation.

### Related Resources
- [Full Installation Guide](/getting-started/installation/)
- [LLM Provider Configuration](/configuration/llm-providers/)
- [Mirror Pod Testing Overview](/features/mirror-pod/)
- [K8sGPT vs Kure Monitor Comparison](/comparisons/k8sgpt-vs-kure/)
