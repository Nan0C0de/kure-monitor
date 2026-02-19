"""
Registry of 20 curated Kyverno policies managed by Kure Monitor.

Each policy definition includes metadata and a reference to its Jinja2 template file.
User configuration (enabled, mode, exclusions) is stored in PostgreSQL.
"""

KYVERNO_POLICIES = [
    # --- Pod Security (8 policies) ---
    {
        "policy_id": "disallow-privileged",
        "display_name": "Disallow Privileged Containers",
        "category": "Pod Security",
        "description": "Prevents containers from running in privileged mode, which grants full access to the host system.",
        "severity": "high",
    },
    {
        "policy_id": "require-non-root",
        "display_name": "Require Non-Root User",
        "category": "Pod Security",
        "description": "Requires containers to run as a non-root user to minimize privilege escalation risks.",
        "severity": "high",
    },
    {
        "policy_id": "disallow-host-namespaces",
        "display_name": "Disallow Host Namespaces",
        "category": "Pod Security",
        "description": "Blocks pods from using host namespaces (hostNetwork, hostPID, hostIPC) which break container isolation.",
        "severity": "high",
    },
    {
        "policy_id": "restrict-host-ports",
        "display_name": "Restrict Host Ports",
        "category": "Pod Security",
        "description": "Prevents containers from binding to host ports, reducing the attack surface on cluster nodes.",
        "severity": "medium",
    },
    {
        "policy_id": "disallow-privilege-escalation",
        "display_name": "Disallow Privilege Escalation",
        "category": "Pod Security",
        "description": "Ensures containers cannot gain more privileges than their parent process via allowPrivilegeEscalation.",
        "severity": "high",
    },
    {
        "policy_id": "require-drop-all-capabilities",
        "display_name": "Require Drop All Capabilities",
        "category": "Pod Security",
        "description": "Requires containers to drop all Linux capabilities and only add back specific ones explicitly.",
        "severity": "medium",
    },
    {
        "policy_id": "restrict-seccomp",
        "display_name": "Restrict Seccomp Profiles",
        "category": "Pod Security",
        "description": "Requires pods to use RuntimeDefault or Localhost Seccomp profiles to restrict system calls.",
        "severity": "medium",
    },
    {
        "policy_id": "restrict-apparmor",
        "display_name": "Restrict AppArmor Profiles",
        "category": "Pod Security",
        "description": "Requires containers to specify an AppArmor profile (runtime/default or localhost) for mandatory access control.",
        "severity": "medium",
    },

    # --- Best Practices (6 policies) ---
    {
        "policy_id": "require-resource-limits",
        "display_name": "Require Resource Limits",
        "category": "Best Practices",
        "description": "Requires all containers to specify CPU and memory limits to prevent resource exhaustion.",
        "severity": "medium",
    },
    {
        "policy_id": "require-resource-requests",
        "display_name": "Require Resource Requests",
        "category": "Best Practices",
        "description": "Requires all containers to specify CPU and memory requests for proper scheduling.",
        "severity": "medium",
    },
    {
        "policy_id": "require-liveness-probes",
        "display_name": "Require Liveness Probes",
        "category": "Best Practices",
        "description": "Requires all containers to define liveness probes for automatic restart on failure.",
        "severity": "low",
    },
    {
        "policy_id": "require-readiness-probes",
        "display_name": "Require Readiness Probes",
        "category": "Best Practices",
        "description": "Requires all containers to define readiness probes so traffic is only sent to ready pods.",
        "severity": "low",
    },
    {
        "policy_id": "require-labels",
        "display_name": "Require Labels",
        "category": "Best Practices",
        "description": "Requires pods to have standard labels (app.kubernetes.io/name) for identification and management.",
        "severity": "low",
    },
    {
        "policy_id": "disallow-latest-tag",
        "display_name": "Disallow Latest Tag",
        "category": "Best Practices",
        "description": "Prevents use of the :latest image tag which makes deployments non-reproducible and harder to debug.",
        "severity": "medium",
    },

    # --- Image Security (3 policies) ---
    {
        "policy_id": "restrict-image-registries",
        "display_name": "Restrict Image Registries",
        "category": "Image Security",
        "description": "Restricts container images to trusted registries only, preventing use of unknown or untrusted sources.",
        "severity": "high",
    },
    {
        "policy_id": "disallow-default-namespace",
        "display_name": "Disallow Default Namespace",
        "category": "Image Security",
        "description": "Prevents deploying resources to the default namespace, enforcing proper namespace organization.",
        "severity": "low",
    },
    {
        "policy_id": "require-image-pull-always",
        "display_name": "Require Always Pull Images",
        "category": "Image Security",
        "description": "Requires imagePullPolicy to be Always, ensuring the latest image is pulled and credentials are verified.",
        "severity": "low",
    },

    # --- Networking (3 policies) ---
    {
        "policy_id": "restrict-nodeport",
        "display_name": "Restrict NodePort Services",
        "category": "Networking",
        "description": "Prevents creation of NodePort services which expose ports directly on cluster nodes.",
        "severity": "medium",
    },
    {
        "policy_id": "restrict-hostpath",
        "display_name": "Restrict HostPath Volumes",
        "category": "Networking",
        "description": "Blocks pods from mounting hostPath volumes which can access sensitive host filesystem data.",
        "severity": "high",
    },
    {
        "policy_id": "require-network-policies",
        "display_name": "Require Network Policies",
        "category": "Networking",
        "description": "Ensures namespaces have NetworkPolicy resources defined to control pod-to-pod traffic.",
        "severity": "medium",
    },
]
