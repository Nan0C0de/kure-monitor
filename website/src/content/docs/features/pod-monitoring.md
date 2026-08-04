---
title: Pod Monitoring
description: Real-time pod failure detection with AI-generated troubleshooting, live logs, and manifest inspection.
---

Kure continuously watches all pods across your cluster and detects failures the moment they happen.

## Detected failure types

| Failure reason | Description |
|----------------|-------------|
| `CrashLoopBackOff` | Container keeps crashing and restarting |
| `ImagePullBackOff` | Unable to pull container image |
| `ErrImagePull` | Error during image pull |
| `CreateContainerError` | Error creating container |
| `RunContainerError` | Error running container |
| `OOMKilled` | Container killed due to out of memory |
| `Pending` | Pod stuck in pending state (after `agent.pendingGracePeriod`) |
| `FailedScheduling` | Cannot schedule pod to any node |
| `FailedMount` | Volume mount failure |

## How AI solutions are generated

1. Agent detects pod failure via the Kubernetes watch API
2. Agent collects context: events, logs (last 100 lines), manifest, container statuses
3. Agent POSTs to backend (`/api/pods/failed`)
4. Backend checks exclusion rules
5. Backend generates a solution:
   - If LLM configured → send context to the AI provider
   - Otherwise → use rule-based solutions
6. Backend stores in PostgreSQL
7. Backend broadcasts via WebSocket to the frontend
8. Frontend renders the failure card

The solution always includes:

- **Diagnosis** — what's wrong
- **Step-by-step fix**
- **Prevention tips**
- **Useful kubectl commands**

## Pod details

Click a failed pod to see:

- **Pod metadata** — node, phase, creation time
- **Error details** — failure reason and message
- **Container statuses** — state, image, restart count
- **Recent events** — Kubernetes events with timestamps
- **AI solution** — the generated guide
- **Pod manifest** — with lines highlighted that the AI referenced

## Live logs

1. Expand the pod row
2. Click **Logs**
3. Pick a container (if multi-container)
4. Pick a tail length (50 / 100 / 500 / 1000 / 2000 lines)
5. Toggle **Previous container** to see logs from a crashed previous instance

You can:

- Download logs as a text file
- Refresh / scroll to bottom
- Switch container without leaving the panel

Logs stream over Server-Sent Events at `/api/pods/{ns}/{name}/logs/stream`.

## Pod lifecycle actions

| Action | Effect |
|--------|--------|
| **Mark as Investigating** (eye icon) | Show the rest of the team that someone is on it |
| **Mark as Resolved** (checkmark) | Move to history |
| **Ignore** | Hide from active view |
| **Restore** | Move back from history or ignored |
| **Retry AI** | Regenerate the AI solution with fresh context |
| **Dismiss** | Drop the failure |

Configure auto-cleanup of resolved and ignored pods from **Admin → Settings**.

## Exclusions

Stop monitoring noisy namespaces or short-lived pods from **Admin → Suppressions**:

- **Namespace exclusions** — e.g. `kube-system`, `kube-public`, `kure-system`
- **Pod patterns** — wildcards: `test-*`, `*-job-*`, `debug-*`

## Pending grace period

Pods that enter `Pending` are flagged only after `agent.pendingGracePeriod` seconds have elapsed (default `120`). This avoids paging on transient pod creation latency.

```yaml
agent:
  pendingGracePeriod: 120  # seconds
```

## Mirror pod testing

For any failing pod with an AI solution, you can [deploy a mirror pod](/features/mirror-pod/) — a temporary copy with the AI fix applied — to verify the fix works before committing to git.
