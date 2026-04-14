# Changelog

All notable changes to Kure Monitor are documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2026-04-14

This release contains **two breaking changes** (auth overhaul, cluster metrics
removal). See [docs/MIGRATING-2.2-TO-2.3.md](docs/MIGRATING-2.2-TO-2.3.md) for
the upgrade guide.

### Changed

- **BREAKING: Auth overhaul.** The legacy single-key `AUTH_API_KEY` /
  `auth.apiKey` model has been removed. The dashboard now uses **user
  accounts**: on first install, visitors are prompted to create an **admin**
  account, and the admin invites further users with **read**, **write**, or
  **admin** roles. Agent and security scanner authenticate to the backend with
  a separate shared **`SERVICE_TOKEN`** (`X-Service-Token` header;
  `?token=<value>` for WebSocket).
  The Helm chart auto-generates both tokens in a `<release>-bootstrap` Secret
  on first install and preserves them across `helm upgrade` via `lookup`. Raw
  k8s manifests ship a placeholder `k8s/bootstrap-secret.yaml` whose values
  must be replaced with `openssl rand -hex 32` output before applying.
- **LLM provider model refresh.** Latest three models surfaced per provider:
  - OpenAI: `gpt-5`, `gpt-5-mini` (default), `gpt-4.1`
  - Anthropic: `claude-opus-4-5`, `claude-sonnet-4-5` (default), `claude-haiku-4-5`
  - Gemini: `gemini-2.5-pro`, `gemini-2.5-flash` (default), `gemini-2.5-flash-lite`
  - Ollama: `llama3.3`, `llama3.2` (default), `qwen2.5`
  - Groq: unchanged

### Added

- **New LLM provider: GitHub Copilot (GitHub Models).** OpenAI-compatible API
  served at `https://models.github.ai/inference`, authenticated with a GitHub
  fine-grained Personal Access Token with the `Models` permission. Aliases:
  `copilot`, `github`, `github_models`. Default model: `openai/gpt-5-mini`.
  Example models include `openai/gpt-5`, `openai/gpt-5-mini`, and
  `anthropic/claude-sonnet-4`.

### Removed

- **BREAKING: Cluster metrics feature removed.** The Monitoring tab, cluster
  metrics ingestion, pod metrics history, and the `metrics-server` dependency
  have been removed. The agent no longer collects or reports metrics. The
  `agent.clusterMetrics` Helm values have been removed and will be silently
  ignored if set. Only `/api/metrics/security-scan-duration` (a Prometheus
  scrape for scanner duration) remains on the metrics endpoint.

### Fixed

- **Admin user couldn't see Admin tab.** `/api/auth/me` returns
  `{user: {...}}` (wrapped), but `AuthContext.js` was calling `setUser(me)`
  directly so `user.role` was always `undefined` and the Admin tab never
  rendered. Fixed by unwrapping `me.user` across all four auth flows
  (refresh, login, setup, accept-invitation).
- **Log-Aware Troubleshoot ordering.** For CrashLoopBackOff and OOMKilled
  pods, the Log-Aware Troubleshoot section now renders **above** the
  AI-Generated Solution (it was previously rendering below it).

## [2.2.0] - 2026-03-26

- Mirror pod testing: deploy a temporary copy of a failing pod with
  AI-generated fixes applied to test before committing to Git
- Mirror pod manifest editor: review and modify AI-generated fixes before
  deploying
- Admin-configurable mirror pod TTL with auto-cleanup (default 3 minutes)
- Comprehensive dark theme improvements across 14+ components
- Security fix manifest cleanup: strips Kubernetes runtime fields before LLM
  analysis
- Improved diff algorithm ignores whitespace-only changes
- Code block rendering fix for react-markdown v9 compatibility
- Exclusions tab renamed to Suppressions in admin panel
- Backend RBAC updated with pod create/delete and event list permissions for
  mirror pod feature
- **BREAKING**: removed `auth.apiKey` in favor of the bootstrap Secret model
  (fully overhauled in 2.3.0)

[2.3.0]: https://github.com/Nan0C0de/kure-monitor/releases/tag/v2.3.0
[2.2.0]: https://github.com/Nan0C0de/kure-monitor/releases/tag/v2.2.0
