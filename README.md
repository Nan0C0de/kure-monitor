# Kure Monitor

[![Artifact Hub](https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/kure-monitor)](https://artifacthub.io/packages/search?repo=kure-monitor)

📚 **Official Website & Documentation:** [https://kuremonitor.com](https://kuremonitor.com)

> **The Kubernetes AI observability platform. Instantly detect pod failures and misconfigurations with AI-powered troubleshooting. Run fully air-gapped with local LLMs (Ollama/vLLM) or bring your own key for OpenAI, Anthropic, and Gemini.**

![Kure Monitor Demo](docs/images/demo.gif)

### AI Advice

Scan running, healthy workloads — and cluster flows — for architectural mismatches a passing readiness probe will never surface. Kure suggests concrete improvements, each with rule-based evidence and a plain-language explanation of *why* it matters.

![AI Advice](docs/images/ai-advice.gif)

### Mirror Pod Testing

Deploy a temporary copy of a failing pod. Manually edit the manifest and deploy temporary pod to check if everything is working.

![Mirror Pod](docs/images/mirror-pod.gif)

## Why Kure?

Unlike tools such as K8sGPT that are CLI-focused, Kure gives you a unified web dashboard combining real-time failure diagnosis, security scanning, and AI-powered fixes in one place. It also supports Ollama for fully local, air-gapped LLM inference — so your cluster data never leaves your network.

## Features

**Core Diagnosis**
- **AI-Powered Troubleshooting** — Get contextual solutions generated from pod events, logs, and manifest analysis using OpenAI, Anthropic, Groq, Google Gemini, GitHub Copilot (GitHub Models), or Ollama
- **Real-time Failure Detection** — Know immediately when pods enter CrashLoopBackOff, ImagePullBackOff, Pending, OOMKilled, or other failure states
- **Security Scanning** — 50+ checks including privileged containers, host namespace access, dangerous capabilities, missing seccomp/AppArmor profiles, root containers, RBAC misconfigurations, untrusted image registries, and missing resource limits
- **Pod Lifecycle Management** — Track pods through investigating, resolved, and ignored states with configurable history retention

**Dashboard**
- **Diagram Tab** — Interactive Kubernetes topology graph. Switch between per-namespace and per-workload views, click any node to view its manifest, click an edge to focus that path (highlights ancestors and descendants, dims everything else)
- **Live Pod Logs** — Stream logs in real-time with container selection
- **Export Findings** — Export security findings to CSV, JSON, and PDF
- **Slack & Teams Notifications** — Get alerted when failures occur
- **Dashboard Authentication** — User accounts with read/write/admin roles, session cookies, and rate-limited login
- **Prometheus Metrics** — `/metrics` endpoint with optional ServiceMonitor support

## Limitations

Kure is focused on failure diagnosis, not general observability:

- **No Prometheus dependency** — Kure works standalone; it doesn't require or replace Prometheus
- **Not a metrics platform** — No time-series data, no alerting rules, no historical dashboards
- **Not a log aggregator** — Logs are fetched on-demand, not stored or indexed
- **Single cluster only** — Monitors one Kubernetes cluster per installation

Kure complements your existing observability stack (Prometheus, Grafana, Datadog) — it doesn't replace it.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a detailed history of updates and releases.

## Documentation

For full documentation, including Architecture, Configuration, Authentication, and Troubleshooting, please visit our **[Official Website Documentation](https://kuremonitor.com/)**.

## Sponsor

If you find Kure Monitor useful, consider supporting its development:

<a href="https://github.com/sponsors/igor-koricanac">
  <img src="https://img.shields.io/badge/Sponsor-❤-ea4aaa?style=for-the-badge&logo=github" alt="Sponsor igor-koricanac" />
</a>

## License

Licensed under the [Apache License 2.0](LICENSE).

"Kure Monitor" is a trademark of Igor Koricanac. See [LICENSE](LICENSE) for trademark details.
