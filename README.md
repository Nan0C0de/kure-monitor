# Kure 🩺

**Real-time Kubernetes health agent with AI-assisted diagnostics.**

`kure` is a lightweight daemon that continuously monitors your Kubernetes cluster, detects problems with pods, nodes, and other resources, and immediately reports them to a central frontend interface — along with an AI-generated suggestion for how to fix the issue.

---

## 🚀 Features

- ⚡ Real-time detection of common Kubernetes issues (CrashLoopBackOff, ImagePullBackOff, Pending, etc.)
- 🧠 AI-powered suggestions for fixing each detected problem (via OpenAI)
- 📊 Web dashboard to display the cluster’s current health
- 🔁 Continuous monitoring via Kubernetes API (no polling)
- 🔒 Runs securely inside the cluster with RBAC and namespace awareness

---

## 📦 Architecture Overview

```text
+-------------+       +--------------+       +---------------+       +------------------+
| kure-agent  | --->  | kure-api     | --->  | OpenAI (GPT)  |       | kure-web (UI)    |
| (in-cluster)|       | (backend API)|       | Suggest Fixes |       | Table of Issues  |
+-------------+       +--------------+       +---------------+       +------------------+
       |                                                        ^
       | <--- Watches Pods, Nodes, Events ----------------------|
