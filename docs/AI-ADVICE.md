# AI Advice

The **AI Advice** feature analyses running, healthy workloads and emits
architectural-mismatch findings -- things a passing readiness probe will
never tell you. The user triggers a scan from the Kure UI scoped to a
namespace, workload, or pod, and the backend runs a pipeline of
detectors over the live cluster state. Each finding includes the
detector's rule-based evidence and an optional LLM-generated explanation
that walks through *why* the pattern is a smell and what to do about it.

![AI Advice demo](images/ai-advice.gif)

AI Advice is the **proactive** counterpart to Kure's existing pod-failure
solutions, which are reactive and only fire on broken pods. AI Advice
looks at pods that are *passing* their liveness/readiness checks and
asks a different question: "is this Kubernetes shape the right shape for
what this workload actually does?"

## What it works on without anything extra

AI Advice ships with seven detectors. **Four of them work today on any
Kubernetes cluster** -- no special CNI, no extra components, just the
Kubernetes API kure-monitor already talks to.

### Layer 1 detectors (manifest-only)

These read your manifests and pod spec. They are cheap, deterministic,
and always on.

- **`deployment-hpa-burst-mismatch`** -- detects HPAs that are wired in a
  way that defeats themselves. Collapsed range (`minReplicas == maxReplicas`),
  CPU-only HPA with a 60-second stabilization window on a bursty
  workload, or an HPA attached to a Deployment whose pod template mounts
  a `ReadWriteOnce` PVC.
- **`db-connections-per-replica`** -- looks for database pool-size env
  vars (`DATABASE_POOL_SIZE`, `SQLALCHEMY_POOL_SIZE`, `HIKARI_MAXIMUM_POOL_SIZE`,
  and friends), multiplies by the worst-case replica count from any
  attached HPA, and flags totals that would exhaust a typical Postgres
  or MySQL connection budget.
- **`startup-io-amplification`** -- flags workloads where every replica
  re-runs the same one-time startup work: migrations, model/artifact
  downloads, `git clone` into an emptyDir. On a multi-replica workload
  this means N copies of the same work and N times the blast radius
  when the upstream rate-limits.

### Bonus Layer 2 detector that needs only pod data

- **`ephemeral-processes`** -- looks at pod restart counts and pod ages
  across a workload's owned pods. Fires when pods are churning -- usually
  `CrashLoopBackOff`, aggressive HPA scale-in, or node-pressure
  evictions. Doesn't need anything beyond what the kube-apiserver
  already gives kure-monitor.

That's 4 of 7 detectors covered with **zero infrastructure beyond a
running Kure install**.

## What unlocks with Cilium + Hubble

The remaining three detectors -- `fan-out-pattern`,
`websocket-on-deployment`, and `all-to-all-replicas` -- answer questions
the kube-apiserver simply does not know the answer to:

- which pods are actually opening connections to which other pods, right
  now;
- whether those connections are short request/responses or long-lived
  streams;
- whether replicas of the same Deployment are talking peer-to-peer.

That kind of per-flow visibility comes from
[**Cilium**](https://cilium.io/), an eBPF-based CNI, and its
observability layer, [**Hubble**](https://docs.cilium.io/en/stable/observability/hubble/).
Hubble exposes per-flow metadata through the Hubble Relay gRPC API,
which kure-monitor consumes through its `HubbleClient` abstraction.

This is **optional**. If your cluster doesn't run Cilium, the three
flow-dependent detectors stay silent and the rest of AI Advice keeps
working. The admin panel marks them with a "Requires Hubble" badge so
you know what you're missing, and the Advice tab shows a small banner
telling you how many detectors are gated.

The deep-dive on Cilium installation, the Hubble-dependent detectors,
configuration knobs, and troubleshooting lives in a separate document:

- [AI Advice -- Layer 2 Integration Guide](./AI-ADVICE-LAYER2.md)

## Triggering a scan

From the Kure UI, open the **Advice** tab and pick a scope:

- **Namespace only** -- runs every enabled detector over every workload
  in that namespace.
- **Workload** (namespace + kind + name) -- narrows context to one
  Deployment / StatefulSet / DaemonSet and the resources it touches
  (its HPA, PDBs, Services with matching selectors, NetworkPolicies in
  the namespace, referenced PVCs and ConfigMaps).
- **Pod** -- not yet exposed in the UI; reserved for a future slice
  once the topology service exposes per-workload pod listing.

Each scan persists its findings in the `advice_findings` table and
broadcasts them over the WebSocket so other open browser tabs update
live. Stale, non-dismissed findings for the scope are wiped before each
re-scan so resolved issues disappear from the list. Dismissed findings
are preserved across rescans -- they will not reappear unless you click
**Restore** in the dismissed view.

## Reading a finding

Each finding card shows:

- a **severity badge** (info, low, medium, high);
- the **detector id** as a small monospace chip (e.g.
  `deployment-hpa-burst-mismatch`) so you can map UI signals back to
  this document;
- a **category** chip (`scaling`, `workload-pattern`, `networking`,
  `startup`, `reliability`);
- a one-line **summary** with the resource (e.g. `Deployment/api in ns-foo`);
- collapsible **evidence** -- the structured facts the detector reacted
  to (replica counts, env-var names, flow counts, etc.). This is the
  source of truth and the only data the LLM is allowed to cite;
- the **recommended change**, written by the detector;
- an LLM-rendered **explanation** in three sections (Why this matters,
  Evidence, Recommended change), if an LLM provider is configured. The
  explainer's prompt forbids the model from inventing facts not present
  in the evidence dict;
- a **confidence** score from the detector. Detectors that rely on hard
  signals (collapsed HPA range, ReadWriteOnce PVC) report higher
  confidence than heuristic ones (suspect command substrings, CPU-only
  HPA on a busy workload).

## Disabling individual detectors

Some detectors will fire on patterns that are deliberate in your
environment (e.g. an internal gateway that *is* meant to fan out to many
destinations). Rather than dismissing the same finding on every rescan,
you can disable the detector entirely from the **Settings -> AI Advice
-- Detector Settings** section of the admin panel.

The toggle is persisted as a single row in the `app_settings` table
(key `advice_detector_enabled`, value is a JSON map of detector id ->
bool). It is read with a short TTL cache on every scan, so flipping a
toggle takes effect on the next scan -- no backend restart needed.

Disabling a detector does not dismiss its existing findings. Use the
existing dismiss/restore controls on each finding card for that.

## Exporting findings

From the Advice tab, the **Export** menu downloads the current findings
list (honouring the active filters, including `Show dismissed`) as
JSON or CSV.

- JSON is the same wire shape served by `GET /api/advice/findings`
  -- a single object with a `findings` array of records.
- CSV has one row per finding with the columns: `id, created_at, severity,
  category, detector_id, namespace, resource_kind, resource_name, title,
  summary, confidence, dismissed, recommended_change, explanation,
  evidence_json`. The last column is the `evidence` dict serialized as
  a JSON string so spreadsheets can keep it intact.

The download filename includes the date so successive exports don't
overwrite.

## Privacy and LLM cost

AI Advice calls the configured LLM provider once per finding to
generate the explanation. There is no other LLM call in the flow --
detectors themselves are pure rules. If no LLM provider is configured
the scan still runs and every finding ships with `explanation: null`;
the rule-based fields are unaffected.

The LLM prompt only includes the redacted finding payload (detector id,
category, severity, resource identifiers, title, summary, evidence,
recommended change). It does **not** include the workload's manifest,
pod spec, environment variables, or any other manifest content beyond
what the detector chose to put in `evidence`. That keeps prompt
contents small, predictable, and free of accidental secret leakage.

## References

- [AI Advice -- Layer 2 Integration Guide](./AI-ADVICE-LAYER2.md) --
  Cilium + Hubble deep-dive.
- [Topology Diagram](./DIAGRAM.md) -- the read-only view that pairs
  well with Advice findings for "why is the cluster shaped like this?"
  investigations.
- Backend code: `kure-monitor/backend/services/advice/`.
- Frontend code: `kure-monitor/frontend/src/components/AdvicePanel.js`,
  `AdviceFindingCard.js`, `AdviceScopePicker.js`, and
  `admin/AdviceDetectorSettings.js`.
