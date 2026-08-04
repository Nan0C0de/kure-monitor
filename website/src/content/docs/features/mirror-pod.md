---
title: Mirror Pod Testing
description: Deploy a temporary copy of a failing pod with the AI-suggested fix applied — verify before committing to git.
---

Mirror Pod Testing lets you deploy a **temporary copy** of a failing pod with the AI-generated fix applied. The mirror runs alongside the original pod under a different name, is excluded from monitoring and security scanning, and auto-deletes after a configurable TTL.

This closes the gap between "the AI says do X" and "I actually merged the fix into git" — you can verify the fix works in your real cluster, with your real config, before touching source control.

## How it works

1. Expand a failing pod and click **Test Fix**
2. The AI generates a fixed YAML manifest based on the failure context (events, logs, current manifest)
3. (Optional) Click **Edit Manifest** to review and tweak the fix
4. Click **Deploy** — backend creates a temporary mirror pod with the fix applied
5. Watch the mirror pod status with a live countdown
6. Mirror auto-deletes after the TTL (default: 3 minutes)

## Features

- **AI-generated manifest fixes** based on failure context (events, logs, current manifest)
- **Manifest editor** to review and modify the fix before deploying
- **Cleanup** — strips Kubernetes runtime noise (auto-injected tolerations, service-account tokens, scheduler fields) from the fixed manifest
- **Configurable TTL** (30 seconds to 60 minutes) via the Admin panel
- **Live status tracking** with a countdown timer
- **Auto-excluded** from monitoring and security scanning so the mirror doesn't clutter your dashboard
- **Manual delete** — clean up early without waiting for the TTL

## Configuration

**Mirror pod TTL:**

1. **Admin Panel → Settings**
2. Adjust **Mirror Pod TTL** (default: 180 seconds)
3. Valid range: 30 – 3600 seconds

Mirror pods are deleted as soon as the TTL expires. Cleanup runs as a background task in the backend.

## Requirements

The backend ServiceAccount needs pod create/delete permissions. The Helm chart's RBAC includes these by default:

```yaml
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "create", "delete"]
- apiGroups: [""]
  resources: ["pods/log"]
  verbs: ["get"]
- apiGroups: [""]
  resources: ["events"]
  verbs: ["list"]
```

If you installed via raw manifests without the bundled RBAC, mirror pod deploys will fail with 403.

## Roles

- **`read`** users see the manifest preview but **cannot deploy** the mirror.
- **`write`** users… same as `read` for mirror pods (admin-only).
- **`admin`** users can preview, deploy, and delete mirror pods.

The "Test Fix" button only appears for users with the right role *and* when the pod failure has an AI solution.

## API

All mirror endpoints live under `/api/mirror/`. See the [API Reference](/reference/api/#mirror-pod-testing) for full request and response shapes.

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/mirror/preview/{pod_id}` | Generate AI-fixed manifest preview |
| `POST` | `/api/mirror/deploy/{pod_id}` | Deploy mirror pod (admin) |
| `GET` | `/api/mirror/status/{mirror_id}` | Mirror status + countdown |
| `DELETE` | `/api/mirror/{mirror_id}` | Delete early (admin) |
| `GET` | `/api/mirror/active` | List currently active mirrors |
| `GET / PUT` | `/api/admin/settings/mirror-ttl` | Read or change the default TTL |

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| **"Test Fix" button missing** | Logged in as `read` / `write` (admin only); or the pod has no AI solution yet |
| **Mirror fails to deploy** | Backend RBAC missing pod create/delete; namespace quota exceeded; image pull error (mirror uses the same image as the original) |
| **Stuck in `Pending`** | Node selectors / affinity from the original can't be satisfied; resources unavailable |
| **Not auto-deleting** | Backend pod isn't running (cleanup is a background task); check backend logs for cleanup errors |

See [Troubleshooting](/reference/troubleshooting/#mirror-pod-issues) for full debugging steps.
