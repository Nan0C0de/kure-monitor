# Changelog

All notable changes to Kure Monitor are documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

> **Note:** The `k8s/` (raw Kubernetes manifests) and `examples/` (pod-failure
> test cases) directories have been removed. Deploy via Helm only — see the
> [Installation guide](docs/MIGRATING-2.2-TO-2.3.md) or the website. Older
> entries below that reference `kubectl apply -f k8s/...` are preserved as
> historical context for upgrades from prior versions; substitute
> `helm upgrade` for the equivalent action.

## [2.4.1] - 2026-05-20

Headline feature: **optional feature toggles**. The four dashboard features
(Pod Monitoring, Security Scan, Diagram, AI Advice) can now be enabled or
disabled individually via Helm values. All four default to `true`, so existing
deployments behave identically. Disabling a feature hides its dashboard tab
and, where applicable, skips deploying any workloads, RBAC, and
NetworkPolicies dedicated to it.

No breaking changes. No RBAC updates. No schema migrations. Drop-in upgrade.

### Added

- **`features.*` Helm values** in `helm/values.yaml` (and matching schema
  entry in `helm/values.schema.json`):

  ```yaml
  features:
    podMonitoring: true   # kure-agent DaemonSet + its RBAC/NetworkPolicy + Pod Monitoring tab
    securityScan: true    # kure-security-scanner Deployment + its RBAC/NetworkPolicy + Security Scan tab
    diagram: true         # Diagram tab (topology view; backend keeps the API)
    aiAdvice: true        # Advice tab (AI advisor; backend keeps the API)
  ```

- **Chart templates gated on the matching flag.**
  - `helm/templates/agent-daemonset.yaml` wrapped in
    `{{- if .Values.features.podMonitoring }}`.
  - `helm/templates/security-scanner-deployment.yaml` wrapped in
    `{{- if .Values.features.securityScan }}`.
  - `helm/templates/rbac.yaml` gates the agent and security-scanner
    ServiceAccounts / ClusterRoles / ClusterRoleBindings behind their
    respective feature flags.
  - `helm/templates/network-policies.yaml` gates the agent and
    security-scanner NetworkPolicies behind their flags, as well as the
    backend ingress rules that exist only to admit traffic from those
    workloads.

- **Backend `/api/config` reports the feature set.** The endpoint now
  returns a `features` dict (`podMonitoring`, `securityScan`, `diagram`,
  `aiAdvice`) so the dashboard can render the correct set of tabs without
  a separate round-trip. Backed by four new `FEATURE_*` settings in
  `backend/core/config.py` (all default `true`); the
  `backend-deployment.yaml` template wires the matching env vars through
  from `.Values.features.*`.

- **Frontend hides disabled tabs.** `Dashboard.js` reads the `features`
  dict from `/api/config` on load and skips rendering any tab whose flag
  is `false`. If the currently selected tab is disabled, it falls back to
  the first enabled tab.

### Notes

- **No breaking changes.** No RBAC updates, no schema migration, no Helm
  values rename. `helm upgrade` is sufficient. Installations that don't
  override `features.*` are bit-identical (apart from the new
  `FEATURE_*` env vars on the backend pod) to a 2.4.0 install.
- **Image tags** for `agent`, `security-scanner`, `backend`, and
  `frontend` move from `2.4.0` to `2.4.1`. Helm values default to the
  matching chart version.
- **Helm only.** The raw `k8s/` manifests were removed in 2.4.0; this
  release continues to ship via Helm exclusively.

## [2.4.0] - 2026-05-13

Headline feature: **AI Advice** — a new dashboard tab that proactively detects
architectural mismatches across two layers. 23 detectors ship out of the box
covering scaling, reliability, networking, data, config, capacity, scheduling,
supply-chain, and startup categories. Scans are LLM-cost-optimised: findings
are persisted with `explanation: null` and the LLM is only called when a user
expands a card (then the explanation is cached, so re-expand never re-calls).

This release also renames the PostgreSQL resources with the `kure-monitor-`
prefix, consolidates the three-role system (`admin`/`write`/`read`) down to
two (`admin`/`member`) via an idempotent migration, and tightens the agent's
WebSocket auth and reconnect behaviour. No API-level breaking changes.

### Added

- **AI Advice tab.** A new "Advice" tab in the dashboard, scoped per
  namespace (and optionally per workload / pod). Selecting a namespace
  auto-runs a scan; narrowing to a workload requires an explicit
  **Run scan** click.
- **23 detectors out of the box** — 7 original + 16 added in this release —
  across categories: scaling, reliability, networking, data, config,
  capacity, scheduling, supply-chain, startup.
- **Layer-1 detectors (20 of 23)** work without any extra infrastructure;
  they read manifests already available via the backend's existing K8s
  permissions.
- **Layer-2 detectors (3-4 of 23)** require Cilium Hubble
  (e.g. `fan-out-pattern`, `websocket-on-deployment`, `all-to-all-replicas`,
  `ephemeral-processes`). The Hubble client is currently a stub; the panel
  shows a **Needs Hubble** badge on those detectors and a coverage banner
  when Hubble is unavailable.
- **Detector Settings admin modal.** Enable/disable any detector, grouped
  by category, with search and bulk **Enable all** / **Disable all** /
  **Reset to defaults**. Hubble-gated detectors are visually marked and
  their toggles disable when Hubble is unavailable.
- **Findings export** to JSON or CSV.
- **Lazy rendering** on the findings list: first 5 cards render initially,
  `IntersectionObserver` loads 5 more as you scroll, with a **Load more**
  link as a fallback.
- New example manifests under `examples/`: `ai-advice-demo.yaml` (one
  Deployment that trips 4 detectors in a single scan), regenerated
  `security-scan-tests.yaml` covering 10 distinct security rules, plus
  `test-insecure-pod.yaml` / `test-recovery.yaml`.
- New top-level docs: `docs/AI-ADVICE.md` and `docs/AI-ADVICE-LAYER2.md`
  (Hubble deep-dive). New website release-notes page
  `website/src/content/docs/release-notes/2-4-0.md`.

### Changed

- **LLM cost optimisation for AI Advice.** Scans run only the detectors and
  persist findings with `explanation: null`. Cards collapse by default;
  expanding a card lazily calls
  `POST /api/advice/findings/{id}/explain`, which generates the explanation
  and caches it on the finding. The call is idempotent — re-expanding never
  re-invokes the LLM.
- **Anti-invention prompt constraints** on the AI Advice explainer: the
  prompt forbids inventing replica counts, image names, container names,
  ports, or labels that are not present in the finding's `evidence` dict.
- **PostgreSQL resources renamed** with the `kure-monitor-` prefix:
  StatefulSet, Service, Secret, and ConfigMap now use
  e.g. `kure-monitor-postgresql`. `helm upgrade` handles the rename; the
  old PVC is orphaned (rebuild-empty migration plan — no data carries over).
- **Role consolidation.** The three-role system (`admin`/`write`/`read`)
  is collapsed to two (`admin`/`member`). The DB migration is idempotent;
  existing `read`/`write` users are auto-mapped to `member` on first boot.
  No manual action required.
- **Login rate limiting is now DB-backed** (`login_attempts` table) instead
  of an in-memory dict, so all backend replicas share state.
- **Service-token rotation paths cleaned up.** The `SERVICE_TOKEN` env var
  is the source of truth and overwrites the DB row on boot if the two
  differ.
- **Agent WebSocket auth defaults to the `X-Service-Token` header**
  instead of `?token=` query param, so the secret never lands in proxy or
  access logs. Falls back to query-param with
  `AGENT_AUTH_VIA_HEADER=false` / `SCANNER_AUTH_VIA_HEADER=false` for
  compatibility with older backend builds.
- **Agent WebSocket reconnects** now use exponential backoff with jitter.
  Tunable via `AGENT_WS_RECONNECT_MAX_SECONDS` and
  `AGENT_WS_HEARTBEAT_SECONDS` env vars.
- **Defensive cleanup across all four services** (backend, agent,
  security-scanner, frontend): Pydantic v2 migration, `asyncio.to_thread`
  + `asyncio.Lock` + `asyncio.wait_for` timeouts on K8s API calls, shared
  `aiohttp.ClientSession`, async shutdown lifecycle in the scanner.
- **Frontend modal accessibility.** Several modals adopted a shared
  `useModalA11y` hook: `role=dialog`, `aria-modal`, focus trap, Escape to
  close, backdrop click to close.
- **Tab order.** AI Advice slots into the dashboard nav as
  Monitoring -> Security -> **Advice** -> Diagram -> Admin (Advice and
  Diagram swapped order).
- **Docs / install path.** Installation is **Helm-only** for end-users —
  the website and this CHANGELOG no longer point at raw `k8s/` manifests.
  CI still uses `k8s/` internally; that's expected.

### Operator action

- **Upgrading from 2.3.x:** the PostgreSQL rename means the old
  `kure-postgresql` StatefulSet / Service / Secret / ConfigMap are no
  longer managed by the chart. `helm upgrade` will reconcile to the new
  `kure-monitor-postgresql` names; the old PVC is orphaned and can be
  deleted at your convenience. Data does not carry over — this is the
  accepted "rebuild empty" migration plan.
- **Users with `read` or `write` roles** are auto-mapped to `member` on
  first backend boot. No manual action needed.
- **Hubble is optional.** If you want the Layer-2 Advice detectors to
  produce findings, install Cilium Hubble. Without it those detectors
  stay greyed out with a **Needs Hubble** badge; the other 20 detectors
  work normally.

## [2.3.4] - 2026-05-10

This release refreshes the LLM-provider experience: the **default provider for
new installs switches from Ollama to Groq**, and the **model catalogs for all
six providers are bumped to current (May 2026) latest models** — both in the
frontend AI Configuration dropdowns and the backend `default_model()` for each
provider. No RBAC changes, no schema migrations, no operator action required.

### Changed

- **Default LLM provider switched from Ollama to Groq.** New installations now
  land on Groq pre-selected in the **Admin Panel → AI Configuration** dropdown.
  Existing installations keep whatever provider is already configured — this
  only affects the initial pre-selection. Implemented in
  `frontend/src/components/LLMSettings.js`.
- **Model lists refreshed across all providers.** Both frontend dropdown
  options and backend `default_model()` (in `backend/llm_providers/`) updated
  to the May 2026 latest models. Backend tests
  (`backend/tests/test_llm_factory.py`,
  `backend/tests/test_copilot_provider.py`) updated to assert the new IDs.

  | Provider | Models (default in **bold**) | Previous |
  |----------|-------------------------------|----------|
  | OpenAI | `gpt-5.5`, **`gpt-5.5-mini`**, `gpt-5.4-mini` | `gpt-5`, `gpt-5-mini`, `gpt-4.1` |
  | Anthropic | `claude-opus-4-7`, **`claude-sonnet-4-6`**, `claude-haiku-4-5` | `claude-opus-4-5`, `claude-sonnet-4-5`, `claude-haiku-4-5` |
  | Google Gemini | `gemini-3.1-pro`, **`gemini-3-flash`**, `gemini-3.1-flash-lite` | `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` |
  | Groq | `openai/gpt-oss-120b`, **`meta-llama/llama-4-scout-17b-16e-instruct`**, `llama-3.3-70b-versatile`, `openai/gpt-oss-20b` | Maverick, Scout, `llama-3.3-70b-versatile` |
  | Ollama | **`llama4:scout`**, `llama3.3`, `qwen3` | `llama3.3`, `llama3.2`, `qwen2.5` |
  | GitHub Copilot | `openai/gpt-5.5`, **`openai/gpt-5.5-mini`**, `anthropic/claude-sonnet-4-6` | `openai/gpt-5`, `openai/gpt-5-mini`, `anthropic/claude-sonnet-4` |

### Notes

- **No breaking changes.** No RBAC updates, no schema migration, no Helm
  values rename. `helm upgrade` (or rolling the new image tags into raw
  manifests) is sufficient.
- **Existing API keys are preserved.** Provider config stored in the database
  is untouched by this release; only the *defaults shown in the UI* changed.

## [2.3.3] - 2026-05-09

This release extends the **Diagram tab** with **RBAC visualization**: a new
Roles mode that graphs Roles / ClusterRoles together with their bindings,
synthesized Permission nodes, and the Users / Groups / ServiceAccounts they
grant access to. The backend ClusterRole gains read permissions on RBAC
resources; cluster operators must reapply RBAC after the upgrade.

### Added

- **Diagram tab: Roles mode.** New top-level mode in the Diagram tab that
  renders an RBAC-focused graph.
  - **Namespace scope** -- pick a namespace + Role; the graph shows the Role,
    its RoleBindings, the synthesized Permission nodes (one per
    `(apiGroup, resource)` tuple, plus `nonResourceURLs`), and the Subjects
    (`User`, `Group`, `ServiceAccount`) the Role is bound to.
  - **Cluster scope** -- pick a ClusterRole; the graph shows the ClusterRole,
    its ClusterRoleBindings, the synthesized Permission nodes, and the
    Subjects the ClusterRole is bound to.
  - **Click a synthesized node** (Permission, Subject:User, Subject:Group)
    -> a new `RbacSummaryModal` opens with the data already present on the
    node (verbs, resource names, kind, namespace) -- no fetch is performed
    because these nodes have no underlying Kubernetes manifest.
  - **Click a real RBAC node** (Role / ClusterRole / RoleBinding /
    ClusterRoleBinding / ServiceAccount) -> the existing manifest side
    panel opens with the live manifest.
- **Backend RBAC topology endpoints** in
  `backend/api/routes_diagram.py`, all gated by `require_read`:
  - `GET /api/diagram/roles` -- lists Roles (per namespace) and ClusterRoles.
  - `GET /api/diagram/role/{namespace}/{name}` -- per-Role graph.
  - `GET /api/diagram/clusterrole/{name}` -- per-ClusterRole graph.
- **Topology service: RBAC graph builder**
  (`backend/services/topology_service.py`). Builds a deterministic graph
  from `Role` / `ClusterRole` rules and `RoleBinding` /
  `ClusterRoleBinding` subjects:
  - `Permission` nodes synthesized one-per-`(apiGroup, resource)` tuple, with
    verbs and `resourceNames` carried in the node metadata.
  - `Subject:User`, `Subject:Group`, and `Subject:ServiceAccount` nodes
    derived from binding subjects.
  - Edges: Role/ClusterRole -> Permission; Role/ClusterRole -> Binding ->
    Subject.
  - Manifest endpoint accepts `Role`, `ClusterRole`, `RoleBinding`,
    `ClusterRoleBinding`, and `ServiceAccount` (in addition to the existing
    workload kinds); rejects synthesized kinds (`Permission`,
    `Subject:User`, `Subject:Group`) with HTTP 400.
- **Frontend.**
  - New `RbacSummaryModal` component for synthesized Permission / Subject
    nodes (no fetch, renders `node.metadata` directly).
  - New `DiagramTab.test.js` and `RbacSummaryModal.test.js` tests; existing
    `TopologyGraph.test.js` extended for the RBAC node types.
  - New node-type styling in `nodeTypes.js` for `Role`, `ClusterRole`,
    `RoleBinding`, `ClusterRoleBinding`, `Permission`, and `Subject:*`.

### Changed

- **OPERATOR ACTION REQUIRED: backend ClusterRole expanded.** The
  `kure-backend` ServiceAccount now needs read access to RBAC resources to
  power the Roles mode:
  - `rbac.authorization.k8s.io`: `roles`, `clusterroles`, `rolebindings`,
    `clusterrolebindings` (get, list).

  After upgrading, reapply RBAC:

  ```bash
  # Helm
  helm upgrade kure-monitor kure-monitor/kure -n kure-system --version 2.3.3

  # Raw manifests
  kubectl apply -f k8s/rbac.yaml
  ```

  Without this step, the new Roles mode of the Diagram tab will return
  HTTP 403. The rest of the dashboard is unaffected. No data migration is
  needed.

- **Image tags** for `agent`, `security-scanner`, `backend`, and
  `frontend` move from `2.3.2` to `2.3.3`. Helm values default to the
  matching chart version.

- **Agent and security-scanner are unchanged** in this release.

### Notes

- This release does **not** grant the backend access to Secret values --
  the Diagram tab's existing "no read access by design" stance for
  Secrets is preserved. The new RBAC permissions only cover the four
  RBAC resources listed above.

## [2.3.2] - 2026-04-27

This release adds the **Diagram tab** -- an interactive Kubernetes topology
graph with click-to-view-manifest and click-to-focus-a-path. The backend
ClusterRole has been expanded; cluster operators must reapply RBAC after
the upgrade.

### Added

- **Diagram tab.** New top-level dashboard tab that renders an interactive
  Kubernetes topology graph. Two modes:
  - **Per-namespace** -- shows all workloads in a namespace and how they
    connect through services, endpoints, ingresses, HPAs, network
    policies, and volume / `envFrom` references.
  - **Per-workload** -- focuses on a single workload (Deployment,
    StatefulSet, DaemonSet, Job, CronJob) plus its ancestors and
    descendants.
  - **Click a node** -> opens a side panel with the live manifest fetched
    from the cluster. Secret nodes intentionally show a "no read access by
    design" info banner instead of fetching (see Security note below).
  - **Click an edge** -> focus that path. Ancestors and descendants stay
    highlighted, everything else dims. Click the same edge again or the
    background to clear.
  - **Group collapse / expand** by `app.kubernetes.io/name` (or `app`)
    label.
  - Layout via [`reactflow`](https://reactflow.dev/) (`^11.11.4`) and
    [`@dagrejs/dagre`](https://github.com/dagrejs/dagre) (`^3.0.0`).
- **Backend topology service** (`backend/services/topology_service.py`).
  Deterministic graph builder from owner refs, label selectors,
  service -> endpoints, ingress backends, HPA targets, NetworkPolicy
  selectors, and volume / envFrom references. 15s in-memory TTL cache.
  EndpointSlice with Endpoints fallback. 21 new unit tests in
  `backend/tests/test_topology_service.py`.
- **Backend diagram API** (`backend/api/routes_diagram.py`). Four new
  endpoints, all gated by `require_read`:
  - `GET /api/diagram/namespaces`
  - `GET /api/diagram/namespace/{ns}`
  - `GET /api/diagram/workload/{ns}/{kind}/{name}`
  - `GET /api/diagram/manifest/{ns}/{kind}/{name}`
- **New Pydantic models** in `backend/models/models.py`: `DiagramNode`,
  `DiagramEdge`, `DiagramGroup`, `DiagramResponse`.
- **Frontend tests.** Two new tests in `TopologyGraph.test.js` cover the
  edge-focus toggle (click to focus, click again / click background to
  clear). Full frontend suite (173 tests) green.

### Changed

- **`ManifestModal` is now reusable.** Added opt-in props: `title`,
  `subtitle`, `infoMessage`, `loading`. All four are backwards-compatible
  -- existing call sites are unaffected.
- **Frontend Jest config moved into `package.json`.** The standalone
  `jest.config.js` was being ignored by Create React App; the equivalent
  config now lives under the `jest` key in `package.json`. A
  `structuredClone` polyfill was added to `setupTests.js` for the new
  topology tests.

### Notes for operators

- **Reapply RBAC after upgrade.** The backend ClusterRole has been
  expanded so the new topology service can read the resources it graphs.
  New permissions for the `kure-backend` ServiceAccount:
  - `core` (`""`): `namespaces` (list), `services / endpoints /
    configmaps / persistentvolumeclaims` (get, list), `serviceaccounts`
    (get).
  - `apps`: extended from `deployments` to `deployments / replicasets /
    statefulsets / daemonsets` (get, list).
  - `batch`: `jobs / cronjobs` (get, list).
  - `networking.k8s.io`: `ingresses / networkpolicies` (get, list).
  - `discovery.k8s.io`: `endpointslices` (get, list).
  - `autoscaling`: `horizontalpodautoscalers` (get, list).

  After upgrading, reapply RBAC:

  ```bash
  # Helm
  helm upgrade kure-monitor kure-monitor/kure -n kure-system --version 2.3.2

  # Raw manifests
  kubectl apply -f k8s/rbac.yaml
  ```

  Without this step, the backend will get HTTP 403s from the Kubernetes
  API and the Diagram tab will fail to load. No data migration is needed.

- **`secrets` is intentionally NOT granted.** Secret nodes in the diagram
  are derived purely from workload spec references (env, envFrom, volume
  mounts). The manifest endpoint hard-rejects `kind=Secret` with HTTP
  403 by design and the UI shows a "no read access by design" info
  banner. This is a deliberate security choice: Kure Monitor never reads
  Secret values.

- **Image tags** for `agent`, `security-scanner`, `backend`, and
  `frontend` move from `2.3.0` to `2.3.2`. Helm values default to the
  matching chart version.

- **Agent and security-scanner are unchanged** in this release.

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

[2.4.1]: https://github.com/Nan0C0de/kure-monitor/releases/tag/v2.4.1
[2.4.0]: https://github.com/Nan0C0de/kure-monitor/releases/tag/v2.4.0
[2.3.4]: https://github.com/Nan0C0de/kure-monitor/releases/tag/v2.3.4
[2.3.3]: https://github.com/Nan0C0de/kure-monitor/releases/tag/v2.3.3
[2.3.2]: https://github.com/Nan0C0de/kure-monitor/releases/tag/v2.3.2
[2.3.0]: https://github.com/Nan0C0de/kure-monitor/releases/tag/v2.3.0
[2.2.0]: https://github.com/Nan0C0de/kure-monitor/releases/tag/v2.2.0
