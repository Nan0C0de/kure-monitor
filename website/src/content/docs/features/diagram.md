---
title: Topology Diagram
description: Interactive Kubernetes topology graph — per-namespace and per-workload — built deterministically from live cluster state.
---

> Introduced in **2.3.2**.

The **Diagram** tab renders an interactive Kubernetes topology graph computed deterministically from live cluster state by the backend. It's read-only and is intended for understanding how a workload fits into the rest of the namespace — which Service routes to it, which Ingress backs it, which HPA scales it, which ConfigMaps / Secrets / PVCs / ServiceAccounts it depends on, which NetworkPolicies select it.

## Modes

### Per-namespace

Pick a namespace from the dropdown. The graph shows every workload in that namespace plus their fan-out: Services, Endpoints / EndpointSlices, Ingresses, HPAs, NetworkPolicies, and the ConfigMaps / Secrets / PVCs / ServiceAccounts the workloads reference.

### Per-workload

Pick a namespace + workload (`Deployment`, `StatefulSet`, `DaemonSet`, `Job`, or `CronJob`). The graph is scoped to that workload plus its ancestors (e.g. Service → Ingress) and descendants (e.g. Pod → ReplicaSet → Deployment).

## Interactions

- **Click a node** → side panel opens with the live manifest fetched from the cluster.
  - For Secret nodes, the panel shows a **"no read access by design"** info banner instead of the manifest body. See [Security model](#security-model) below.
- **Click an edge** → focus that path. Ancestors and descendants stay highlighted; everything else dims. Click the same edge again or click the background to clear.
- **Group collapse / expand** → nodes sharing the same `app.kubernetes.io/name` (or `app`) label can be folded into a group node. Use the chevron on the group header.

## How the graph is built

The backend's `topology_service` walks live Kubernetes API responses and emits a deterministic node + edge list:

| Source | Edge produced |
|--------|---------------|
| `metadata.ownerReferences` | child → parent (Pod → ReplicaSet → Deployment) |
| Service `spec.selector` | Service → Pod (matched by labels) |
| Service → EndpointSlice / Endpoints | Service → backing Pod (concrete) |
| Ingress `spec.rules.*.backend` | Ingress → Service |
| HPA `spec.scaleTargetRef` | HPA → target workload |
| NetworkPolicy `podSelector` | NetworkPolicy → selected Pods |
| Volume `configMap` / `secret` | Pod → ConfigMap / Secret |
| Container `envFrom` / `env.valueFrom` | Pod → ConfigMap / Secret |
| Volume `persistentVolumeClaim` | Pod → PVC |
| Pod `spec.serviceAccountName` | Pod → ServiceAccount |

EndpointSlices are preferred; Endpoints is the fallback for older / smaller clusters.

The result is cached in-memory on the backend with a **15s TTL**, so repeated dashboard interactions don't hammer the API server.

## Security model

The backend **intentionally does not have read access to Secrets**.

- The ClusterRole granted to the `kure-backend` ServiceAccount in `helm/templates/rbac.yaml` and `k8s/rbac.yaml` does **not** include `secrets`.
- The `GET /api/diagram/manifest/{ns}/{kind}/{name}` endpoint hard-rejects any request where `kind=Secret` and returns HTTP 403.
- Secret nodes are still drawn on the graph because they are derived purely from workload spec references (`envFrom`, `env.valueFrom`, volume mounts) — nothing in the Secret object itself is read.
- The frontend handles the 403 by rendering a "no read access by design" info banner in the manifest panel instead of fetching.

This is a deliberate design choice. If you want a tool that surfaces Secret values, Kure Monitor is not it.

## RBAC required

The Diagram feature relies on the backend ServiceAccount being able to list / get the resources it graphs. As of **2.3.2**, the chart and raw manifests both grant:

- **`""` (core)** — `namespaces` (list); `services`, `endpoints`, `configmaps`, `persistentvolumeclaims` (get, list); `serviceaccounts` (get).
- **`apps`** — `deployments`, `replicasets`, `statefulsets`, `daemonsets` (get, list).
- **`batch`** — `jobs`, `cronjobs` (get, list).
- **`networking.k8s.io`** — `ingresses`, `networkpolicies` (get, list).
- **`discovery.k8s.io`** — `endpointslices` (get, list).
- **`autoscaling`** — `horizontalpodautoscalers` (get, list).

If you upgrade an existing 2.3.0 install in-place **without** running `helm upgrade` (or `kubectl apply -f k8s/rbac.yaml`), the backend will get HTTP 403 from the API server when the Diagram tab is opened. Reapply RBAC after upgrade.

## API reference

All endpoints are gated by `require_read` (any logged-in dashboard user can call them).

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/diagram/namespaces` | List namespaces |
| `GET` | `/api/diagram/namespace/{ns}` | Per-namespace graph |
| `GET` | `/api/diagram/workload/{ns}/{kind}/{name}` | Per-workload graph |
| `GET` | `/api/diagram/manifest/{ns}/{kind}/{name}` | Live manifest for a node |

The manifest endpoint returns HTTP 403 for `kind=Secret` by design.

See the [API Reference](/kure-monitor/reference/api/#diagram) for full request/response shapes.

## Limitations

- **Single-cluster only** — same as the rest of Kure Monitor.
- **Snapshot, not stream** — graph is cached for 15s; refresh the page (or switch namespace and back) to force a fresh build.
- **Cross-namespace edges** are followed for ConfigMaps / Secrets / PVCs / ServiceAccounts only when the namespace is explicitly referenced by the workload spec.
