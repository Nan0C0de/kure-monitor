---
title: Topology Diagram
description: Interactive Kubernetes topology graph — per-namespace and per-workload — built deterministically from live cluster state.
---

> Introduced in **2.3.2**. **2.3.3** added a third mode for RBAC visualization (Roles / ClusterRoles, their bindings, and the subjects they grant access to).

The **Diagram** tab renders an interactive Kubernetes topology graph computed deterministically from live cluster state by the backend. It's read-only and is intended for understanding how a workload fits into the rest of the namespace — which Service routes to it, which Ingress backs it, which HPA scales it, which ConfigMaps / Secrets / PVCs / ServiceAccounts it depends on, which NetworkPolicies select it.

## Modes

### Per-namespace

Pick a namespace from the dropdown. The graph shows every workload in that namespace plus their fan-out: Services, Endpoints / EndpointSlices, Ingresses, HPAs, NetworkPolicies, and the ConfigMaps / Secrets / PVCs / ServiceAccounts the workloads reference.

### Per-workload

Pick a namespace + workload (`Deployment`, `StatefulSet`, `DaemonSet`, `Job`, or `CronJob`). The graph is scoped to that workload plus its ancestors (e.g. Service → Ingress) and descendants (e.g. Pod → ReplicaSet → Deployment).

### Roles (added in 2.3.3)

RBAC-focused mode. Two scopes:

- **Namespace** — pick a namespace + Role; the graph shows the Role, its RoleBindings, the synthesized Permission nodes, and the Subjects (`User`, `Group`, `ServiceAccount`) the Role is bound to.
- **Cluster** — pick a ClusterRole; same shape but for ClusterRoles + ClusterRoleBindings.

`Permission` nodes are synthesized one per `(apiGroup, resource)` tuple (plus one per `nonResourceURLs` group). The verbs and any `resourceNames` are carried in `node.metadata` and shown in the summary panel. Subject nodes are derived from binding `subjects[]` entries; for `ServiceAccount` subjects the node still opens the live manifest, but `User` and `Group` subjects have no underlying object so they get a synthesized summary panel instead.

## Interactions

- **Click a node** → side panel opens with the live manifest fetched from the cluster.
  - For Secret nodes, the panel shows a **"no read access by design"** info banner instead of the manifest body. See [Security model](#security-model) below.
  - For synthesized RBAC nodes (`Permission`, `Subject:User`, `Subject:Group`), an `RbacSummaryModal` opens with the data already on the node (verbs, resource names, kind, namespace). No fetch is performed — these nodes have no underlying Kubernetes manifest.
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

The Diagram feature relies on the backend ServiceAccount being able to list / get the resources it graphs. As of **2.3.3**, the chart and raw manifests grant:

- **`""` (core)** — `namespaces` (list); `services`, `endpoints`, `configmaps`, `persistentvolumeclaims` (get, list); `serviceaccounts` (get).
- **`apps`** — `deployments`, `replicasets`, `statefulsets`, `daemonsets` (get, list).
- **`batch`** — `jobs`, `cronjobs` (get, list).
- **`networking.k8s.io`** — `ingresses`, `networkpolicies` (get, list).
- **`discovery.k8s.io`** — `endpointslices` (get, list).
- **`autoscaling`** — `horizontalpodautoscalers` (get, list).
- **`rbac.authorization.k8s.io`** — `roles`, `clusterroles`, `rolebindings`, `clusterrolebindings` (get, list). **Added in 2.3.3** for the Roles mode.

If you upgrade an existing 2.3.0 or 2.3.2 install in-place **without** running `helm upgrade` (or `kubectl apply -f k8s/rbac.yaml`), the backend will get HTTP 403 from the API server when the Diagram tab is opened (for a 2.3.2 → 2.3.3 upgrade, only the Roles mode will fail — the existing modes keep working). Reapply RBAC after upgrade.

## API reference

All endpoints are gated by `require_read` (any logged-in dashboard user can call them).

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/diagram/namespaces` | List namespaces |
| `GET` | `/api/diagram/namespace/{ns}` | Per-namespace graph |
| `GET` | `/api/diagram/workloads/{ns}/{kind}` | Workload names for a kind in a namespace |
| `GET` | `/api/diagram/workload/{ns}/{kind}/{name}` | Per-workload graph |
| `GET` | `/api/diagram/manifest/{ns}/{kind}/{name}` | Live manifest for a node |
| `GET` | `/api/diagram/roles` | List Roles + ClusterRoles (2.3.3+) |
| `GET` | `/api/diagram/role/{ns}/{name}` | Per-Role graph (2.3.3+) |
| `GET` | `/api/diagram/clusterrole/{name}` | Per-ClusterRole graph (2.3.3+) |

The manifest endpoint returns HTTP 403 for `kind=Secret` by design. Synthesized kinds (`Permission`, `Subject:User`, `Subject:Group`) return HTTP 400 because they have no underlying manifest.

See the [API Reference](/kure-monitor/reference/api/#diagram) for full request/response shapes.

## Limitations

- **Single-cluster only** — same as the rest of Kure Monitor.
- **Snapshot, not stream** — graph is cached for 15s; refresh the page (or switch namespace and back) to force a fresh build.
- **Cross-namespace edges** are followed for ConfigMaps / Secrets / PVCs / ServiceAccounts only when the namespace is explicitly referenced by the workload spec.
