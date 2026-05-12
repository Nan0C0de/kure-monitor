# AI Advice -- Layer 2 Integration Guide

The **AI Advice** feature analyses running healthy workloads and emits
architectural-mismatch findings -- things a passing readiness probe will
never tell you, like "this Deployment should be a StatefulSet" or "this
HPA is tuned for stateless work but the Pod is stateful". The user
triggers a scan from the Kure UI scoped to a namespace, workload, or
pod, and the backend runs a pipeline of detectors over the live cluster
state plus (in Layer 2) live network-flow data.

This document covers **Layer 2**: the detectors that need more than
manifests to do their job, and the upstream observability stack
(Cilium + Hubble) they depend on.

## Overview

Layer 1 detectors (`deployment-hpa-burst-mismatch`,
`db-connections-per-replica`, `startup-io-amplification`) live in
`backend/services/advice/detectors/` and operate purely on the YAML
the cluster already has. They are cheap, deterministic, and ship
enabled by default.

Layer 2 detectors operate on **runtime evidence** the API server does
not expose: which pods are actually opening connections to which other
pods, whether those connections are short request/responses or
long-lived streams, whether replicas of the same Deployment are
talking peer-to-peer, and how often pods are restarting.

The first three questions need per-flow visibility -- they cannot be
answered from `kubectl get`. Layer 2 introduces a `HubbleClient`
abstraction in the advice service, with three detectors that consume
flow data and one detector (`ephemeral-processes`) that only needs
pod-level kube state.

## Cilium + Hubble primer

[**Cilium**](https://cilium.io/) is an eBPF-based CNI plugin. It
replaces Calico, Flannel, or whatever CNI your cluster currently uses.
Because it programs the kernel via eBPF, Cilium can see every L3/L4 (and
optionally L7) packet a pod sends or receives without sidecars or a
service mesh.

[**Hubble**](https://docs.cilium.io/en/stable/observability/hubble/) is
Cilium's observability layer. It collects the per-flow metadata Cilium
already has access to (source/dest pod identity, protocol, verdict,
L7 attributes when enabled) and exposes them through two surfaces:

- the `hubble` CLI for ad-hoc inspection (`hubble observe`); and
- the **Hubble Relay** gRPC API, which aggregates flows from every
  node-local Hubble agent into a single cluster-wide stream. This is
  the API kure-monitor's `HubbleClient` will consume.

Hubble **requires Cilium as the CNI**. You cannot bolt Hubble onto
Flannel or Calico. If your cluster runs a different CNI, Layer 2's
flow-dependent detectors will stay dark until you migrate.

Upstream references:

- <https://cilium.io/>
- <https://docs.cilium.io/en/stable/gettingstarted/>
- <https://docs.cilium.io/en/stable/observability/hubble/>

## Installation

This guide does **not** reproduce the upstream install -- the Cilium
docs are the source of truth. Follow the install path that matches
your distro (kind, k3s, EKS, GKE, AKS) from the Getting Started
section linked above, then enable Hubble and the Hubble Relay (the
upstream docs show both Helm flags and `cilium-cli` one-liners).
You'll know it's healthy when `hubble status` prints non-zero flow
counts and `kubectl -n kube-system get svc hubble-relay` shows a
running ClusterIP service.

**Swapping CNI on an existing cluster is disruptive.** Pod network
identity, NetworkPolicy semantics, and IP allocation all change. For
anything beyond a lab, plan a fresh cluster or a per-node
drain-and-replace migration. **kind** is by far the easiest way to
try Layer 2 end-to-end -- a single `cilium install` plus `cilium
hubble enable --ui` on a fresh kind cluster gets you a fully
disposable test rig in minutes.

## Configuring kure-monitor

In the current release the `HubbleClient` interface is wired in but
backed by a **stub** (`StubHubbleClient`) that always returns "Hubble
not configured." The three flow-dependent Layer 2 detectors will
register, run, and consistently emit zero findings. This is
intentional -- the real gRPC client lands in a follow-up slice.

The admin panel surfaces this state explicitly as **"Hubble status: not
configured."** That's how you confirm the stub is in play and not, say,
a broken relay address.

When the real client ships it will read the following environment
variables. **These names are proposed here, not yet honoured by the
backend** -- setting them in the current release has no effect:

| Variable                          | Default                                              | Purpose                                              |
|-----------------------------------|------------------------------------------------------|------------------------------------------------------|
| `CILIUM_HUBBLE_RELAY_ADDRESS`     | `hubble-relay.kube-system.svc.cluster.local:80`      | gRPC endpoint of the Hubble Relay service.           |
| `CILIUM_HUBBLE_TLS_ENABLED`       | `false`                                              | Connect over TLS / mTLS. Required for hardened installs. |
| `CILIUM_HUBBLE_TLS_CA_FILE`       | *(unset)*                                            | Path to the CA bundle that signed the relay cert.    |
| `CILIUM_HUBBLE_TLS_SERVER_NAME`   | *(unset)*                                            | SNI / TLS server name to validate against the cert.  |

The naming follows the `FEATURE_KNOB` convention already used in
`backend/core/config.py` (`FAILURE_LOGS_ENABLED`,
`LLM_MANIFEST_MAX_BYTES`). When the real client lands, these will
appear in that file with the existing `_env_bool` / `os.getenv`
helpers.

## The four Layer-2 detectors

Detector IDs are stable slugs (the `id` class attribute on the
`PatternDetector` subclass) and show up unchanged in the finding's
`detector_id` field and in the admin enable/disable toggle.

### `fan-out-pattern` -- requires Hubble

**Looks for:** a source pod opening flows to an unusually large
number of distinct destinations relative to its peers in the same
workload, over the scan window.

**Evidence emitted:** source pod, count of distinct destinations, and
a sample of top destinations by flow volume.

**True positive:** a worker calling many backends serially when it
could parallelise, or a pre-aggregator that should be split into
smaller queue-driven jobs.

**False positive:** gateways, API aggregators, and egress proxies
fan out by design. Dismiss if the pod's whole job is to talk to many
things.

### `websocket-on-deployment` -- requires Hubble

**Looks for:** long-lived TCP flows (no clean close for the scan
window, or explicit WebSocket upgrade observed at L7) terminating on
pods owned by a **Deployment** rather than a StatefulSet.

**Evidence emitted:** the workload, sample flow durations, peer
identities.

**True positive:** real WebSocket / SSE / gRPC streaming on a
Deployment. Rolling updates drop active connections; scale-in is
indiscriminate because pods have no stable identity. A StatefulSet
(or at minimum a tuned `terminationGracePeriodSeconds`) is the fix.

**False positive:** HTTP long-poll, chunked transfer encoding, or
HTTP/2 connection pooling can look like a persistent session without
being one. Dismiss when the workload is plain stateless HTTP.

### `all-to-all-replicas` -- requires Hubble

**Looks for:** flows where source and destination pod both belong to
the **same Deployment** (matched on owner reference up to the
Deployment). The detector only fires on Deployments; StatefulSets
are excluded from the source set.

**Evidence emitted:** the workload, participating replica pods, flow
counts per pair.

**True positive:** a homegrown consensus, gossip, or shared-cache
layer running on a Deployment. These need stable network identity to
coordinate -- a StatefulSet with a headless Service is the correct
shape.

**False positive:** rare. If it fires on a workload you're sure
isn't peer-coordinating, check for a misclassified sidecar (e.g. a
metrics scraper running as a separate Deployment in the same label
namespace) and dismiss.

### `ephemeral-processes` -- does NOT require Hubble

**Looks for:** workloads whose pods have high cumulative restart
counts combined with a short average pod age across the current
replica set. Pure kube-state -- runs even when Hubble is unavailable.

**Evidence emitted:** restart counts, average pod age, recent
termination reasons when available.

**True positive:** CrashLoopBackOff that hasn't tripped the failure
threshold, OOMKill churn, or HPA scale-down too aggressive for the
workload's startup time.

**False positive:** intentional short-lived batch-style workloads
running under a Deployment instead of a Job, or rolling updates in
progress when the scan ran. Re-scan and confirm persistence.

## Disabling individual detectors

Each detector can be toggled from the **Admin -> AI Advice** panel.
The toggle is persisted in the `app_settings` table under
`advice_detector_enabled` (keyed by detector id). The AdviceEngine
reads the table at the start of every scan -- **no restart needed**;
the next scan picks up the new state. A disabled detector is skipped
entirely; it doesn't run and emit filtered findings, it just never
runs.

## Troubleshooting

**Layer-2 detectors aren't producing any findings.** Check, in order:

1. Admin panel shows "Hubble status: not configured" -- expected
   in the current release; the real client hasn't shipped.
2. After that ships: confirm Cilium is the cluster CNI
   (`kubectl -n kube-system get pods | grep cilium`).
3. Confirm Hubble Relay is reachable from the backend pod
   (`kubectl exec` + `nc -vz hubble-relay.kube-system 80`).
4. If Hubble is mTLS-protected, confirm `CILIUM_HUBBLE_TLS_*` is set
   and the backend has the cert material the relay requires.

**`all-to-all-replicas` keeps flagging my StatefulSet.** It shouldn't.
The detector explicitly only fires when the owning workload is a
Deployment. If you see this, capture the finding payload and file a
bug -- it's a detector defect.

**`websocket-on-deployment` fires on a normal HTTP service.** Most
likely cause is HTTP long-poll or chunked transfer being misclassified
as a persistent session. Dismiss the finding, or disable the detector
for that workload if it's recurring noise.

**Hubble works in `hubble observe` but Kure can't see flows.** Almost
always a relay address mismatch. Double-check
`CILIUM_HUBBLE_RELAY_ADDRESS` resolves and is reachable from inside
the backend pod (not from your laptop). If you exposed the relay on a
non-default port, the `:80` in the default won't match.

## References

- Cilium -- <https://cilium.io/>
- Cilium Getting Started -- <https://docs.cilium.io/en/stable/gettingstarted/>
- Hubble observability -- <https://docs.cilium.io/en/stable/observability/hubble/>
- kure-monitor README -- `../README.md`
- Topology diagram (architectural context) -- [`DIAGRAM.md`](./DIAGRAM.md)
