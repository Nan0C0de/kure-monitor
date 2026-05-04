---
title: Security Scanner
description: 50+ Kubernetes security checks with AI-generated remediation, trusted-registry suppressions, and CSV/JSON/PDF export.
---

The security scanner is a separate Deployment that audits every pod in your cluster on a schedule and on demand. Findings are scored by severity and surfaced on the **Security** tab.

## Sample checks

| Check | Severity | Description |
|-------|----------|-------------|
| Privileged containers | Critical | Container running with elevated privileges |
| Host network | Critical | Pod using host network namespace |
| Host PID | Critical | Pod using host PID namespace |
| Run as root | High | Container running as root user |
| Missing security context | High | No `securityContext` defined |
| Missing resource limits | Medium | No CPU/memory limits set |
| Writable root filesystem | Medium | Root filesystem is writable |
| ServiceAccount token mounted | Low | Default SA token auto-mounted |

50+ checks ship out of the box including dangerous capabilities, missing seccomp/AppArmor profiles, untrusted registries, and RBAC misconfigurations.

## The dashboard

The **Security** tab supports:

- Filter by severity (Critical / High / Medium / Low)
- Filter by namespace
- Click any finding for full remediation steps
- Manual **Rescan** button for on-demand re-scanning

## AI security fixes

For any finding, click **Generate AI Fix**. The LLM gets the finding context and produces:

- A detailed explanation of the security risk
- Step-by-step remediation instructions
- Example YAML patches
- Best-practice recommendations

Backed by `POST /api/security/findings/{finding_id}/fix`.

## Trusted container registries

By default, the scanner flags images pulled from registries it doesn't recognize. Add your registry to the trusted list to suppress those findings.

**Default trusted registries:**

- `docker.io`
- `gcr.io`
- `ghcr.io`
- `quay.io`
- `registry.k8s.io`
- `mcr.microsoft.com`
- `public.ecr.aws`

Add your own from **Admin Panel → Suppressions → Trusted Container Registries**. The scanner automatically rescans when you add or remove an entry.

## Rule exclusions

Two layers:

- **Global** — rule is suppressed everywhere (Admin → Suppressions → Global Rule Exclusions)
- **Per-namespace** — rule is suppressed only in named namespaces (Admin → Suppressions, then add namespace + select rules)

Hold Ctrl/Cmd to multi-select.

## Namespace exclusions

Skip whole namespaces from scanning. Common entries:

- `kube-system`
- `kube-public`
- `kube-node-lease`
- `kure-system`

## Export findings

From the Security tab, click **Export**:

- **CSV** — spreadsheet compatible
- **JSON** — machine readable
- **PDF** — formatted report (good for compliance)

## How the scanner authenticates to the backend

The scanner POSTs findings to `/api/security/findings` with the `X-Service-Token` header. The token is mounted from the `<release>-bootstrap` Secret. See [Authentication](/kure-monitor/configuration/authentication/).
