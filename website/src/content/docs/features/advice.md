---
title: AI Advice
description: Kure Monitor's proactive AI Advice engine with 38+ detectors for hygiene, scheduling, networking, and storage.
---

The **AI Advice** tab is the newest and most proactive feature in Kure Monitor. While normal pod monitoring waits for a pod to crash, the Advice engine scans your healthy and running workloads to find architectural, scheduling, and hygiene issues *before* they cause outages.

## How it works

Kure Monitor currently ships with **38+ advice detectors** covering:
- **Resource Hygiene:** Missing CPU/Memory requests, improper limits, or CPU limit throttling risks.
- **Scheduling & Availability:** Over-concentrated pods, missing pod anti-affinity, or missing disruption budgets.
- **Networking:** Missing readiness probes or overly permissive network policies.
- **Lifecycle & Storage:** Unsafe termination grace periods or emptyDir abuse.

When Kure scans your cluster, it surfaces these findings in the **Advice** tab, categorized into **Active** and **Ignored** lists.

## Lazy AI Explanations

To save on LLM API costs and execution time, Kure Monitor evaluates all 38 detectors using deterministic, blazingly-fast Go code. 

The LLM is only invoked **lazily on card expand**. 
When you click on a specific advice finding, Kure sends the exact `evidence` dictionary to your configured LLM (one call per finding, which is then heavily cached). 

This approach ensures:
1. **Cost Efficiency**: A scan with 500 findings does not cost 500 LLM requests up front.
2. **High Accuracy**: The prompt is strictly constrained to only reference data present in the finding’s `evidence` dict. The AI cannot invent replica counts, image names, ports, or labels. It explains *why* the evidence is problematic and *how* to fix it.
