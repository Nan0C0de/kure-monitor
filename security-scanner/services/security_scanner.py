import asyncio
import logging
import os
from datetime import datetime
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from services.backend_client import BackendClient

logger = logging.getLogger(__name__)


class SecurityScanner:
    # Dangerous capabilities that should never be added
    DANGEROUS_CAPABILITIES = [
        'SYS_ADMIN',      # Full admin access
        'NET_RAW',        # Packet spoofing/sniffing
        'SYS_PTRACE',     # Process tracing/debugging
        'SYS_MODULE',     # Load kernel modules
        'DAC_READ_SEARCH', # Bypass file read permissions
        'NET_ADMIN',      # Network configuration
        'SYS_RAWIO',      # Raw I/O operations
        'SYS_BOOT',       # Reboot system
        'SYS_TIME',       # Modify system clock
        'MKNOD',          # Create device files
        'SETUID',         # Set arbitrary UIDs
        'SETGID',         # Set arbitrary GIDs
    ]

    # Capabilities allowed by Pod Security Standards Restricted policy
    ALLOWED_CAPABILITIES = ['NET_BIND_SERVICE']

    def __init__(self):
        self.backend_url = os.getenv("BACKEND_URL", "http://kure-monitor-backend:8000")
        self.scan_interval = int(os.getenv("SCAN_INTERVAL", "3600"))
        self.backend_client = BackendClient(self.backend_url)
        self.v1 = None
        self.apps_v1 = None
        self.rbac_v1 = None
        self.networking_v1 = None

    def _init_kubernetes_client(self):
        """Initialize Kubernetes client"""
        try:
            # Try in-cluster config first
            config.load_incluster_config()
            logger.info("Using in-cluster Kubernetes config")
        except config.ConfigException:
            try:
                # Fall back to local kubeconfig
                config.load_kube_config()
                logger.info("Using local kubeconfig")
            except config.ConfigException:
                logger.error("Could not configure Kubernetes client")
                raise

        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.rbac_v1 = client.RbacAuthorizationV1Api()
        self.networking_v1 = client.NetworkingV1Api()

    async def start_scanning(self):
        """Start the security scanning loop"""
        logger.info(f"Starting security scanner (scan interval: {self.scan_interval}s)")
        logger.info(f"Backend URL: {self.backend_url}")

        self._init_kubernetes_client()

        while True:
            try:
                logger.info("Starting new security scan...")
                await self.backend_client.clear_security_findings()
                await self.scan_cluster()
                logger.info(f"Security scan completed. Next scan in {self.scan_interval}s")
            except Exception as e:
                logger.error(f"Error during security scan: {e}")

            await asyncio.sleep(self.scan_interval)

    async def scan_cluster(self):
        """Run all security checks"""
        await self.scan_pods()
        await self.scan_deployments()
        await self.scan_services()
        await self.scan_rbac()
        await self.scan_network_policies()
        await self.scan_service_accounts()

    async def scan_pods(self):
        """Scan pods for security issues based on Pod Security Standards and NSA/CISA guidelines"""
        logger.info("Scanning pods for security issues...")
        try:
            pods = self.v1.list_pod_for_all_namespaces()

            for pod in pods.items:
                # Skip pods in kube-system namespace
                if pod.metadata.namespace in ['kube-system', 'kube-public', 'kube-node-lease']:
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"
                pod_name = pod.metadata.name
                namespace = pod.metadata.namespace

                # === Pod-level security checks ===

                # Check for hostNetwork (Baseline)
                if pod.spec.host_network:
                    await self.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "high",
                        "category": "Security",
                        "title": "Pod uses host network namespace",
                        "description": "Pod is using the host network namespace, which exposes the host's network stack to the container and bypasses network policies.",
                        "remediation": "Remove 'hostNetwork: true' unless required for specific use cases like CNI plugins or monitoring agents.",
                        "timestamp": timestamp
                    })

                # Check for hostPID (Baseline)
                if pod.spec.host_pid:
                    await self.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "high",
                        "category": "Security",
                        "title": "Pod uses host PID namespace",
                        "description": "Pod is using the host PID namespace, which allows viewing and signaling all processes on the host.",
                        "remediation": "Remove 'hostPID: true' unless absolutely necessary for debugging or monitoring.",
                        "timestamp": timestamp
                    })

                # Check for hostIPC (Baseline) - NEW
                if pod.spec.host_ipc:
                    await self.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "high",
                        "category": "Security",
                        "title": "Pod uses host IPC namespace",
                        "description": "Pod is using the host IPC namespace, which allows reading shared memory with host processes.",
                        "remediation": "Remove 'hostIPC: true' from the pod specification.",
                        "timestamp": timestamp
                    })

                # Check for hostPath volumes (Baseline) - NEW
                if pod.spec.volumes:
                    for volume in pod.spec.volumes:
                        if volume.host_path:
                            severity = "critical" if volume.host_path.path in ['/', '/etc', '/var', '/root', '/home'] else "high"
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod_name,
                                "namespace": namespace,
                                "severity": severity,
                                "category": "Security",
                                "title": f"HostPath volume mounted: {volume.host_path.path}",
                                "description": f"Volume '{volume.name}' mounts host path '{volume.host_path.path}'. This provides direct access to the host filesystem and can lead to container escape.",
                                "remediation": "Use persistent volumes, configMaps, secrets, or emptyDir instead of hostPath volumes.",
                                "timestamp": timestamp
                            })

                # === Container-level security checks ===
                all_containers = (pod.spec.containers or []) + (pod.spec.init_containers or [])

                for container in all_containers:
                    container_name = container.name
                    sec_ctx = container.security_context

                    # Check for privileged containers (Baseline)
                    if sec_ctx and sec_ctx.privileged:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "critical",
                            "category": "Security",
                            "title": f"Privileged container: {container_name}",
                            "description": f"Container '{container_name}' is running in privileged mode, which grants full access to all host devices and capabilities. This is equivalent to root on the host.",
                            "remediation": "Remove 'privileged: true' from the container's securityContext. Use specific capabilities if needed.",
                            "timestamp": timestamp
                        })

                    # Check for allowPrivilegeEscalation (Restricted) - NEW
                    if not sec_ctx or sec_ctx.allow_privilege_escalation is None or sec_ctx.allow_privilege_escalation:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "high",
                            "category": "Security",
                            "title": f"Privilege escalation allowed: {container_name}",
                            "description": f"Container '{container_name}' allows privilege escalation via setuid binaries or filesystem capabilities.",
                            "remediation": "Set 'allowPrivilegeEscalation: false' in the container's securityContext.",
                            "timestamp": timestamp
                        })

                    # Check for dangerous capabilities (Baseline/Restricted) - NEW
                    if sec_ctx and sec_ctx.capabilities and sec_ctx.capabilities.add:
                        dangerous_caps = [cap for cap in sec_ctx.capabilities.add if cap in self.DANGEROUS_CAPABILITIES]
                        if dangerous_caps:
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod_name,
                                "namespace": namespace,
                                "severity": "high",
                                "category": "Security",
                                "title": f"Dangerous capabilities added: {container_name}",
                                "description": f"Container '{container_name}' adds dangerous capabilities: {', '.join(dangerous_caps)}. These can be used for container escape or privilege escalation.",
                                "remediation": f"Remove dangerous capabilities from the container. Only NET_BIND_SERVICE is allowed in the Restricted policy.",
                                "timestamp": timestamp
                            })

                    # Check for missing capability drop ALL (Restricted) - NEW
                    caps_dropped_all = (
                        sec_ctx and sec_ctx.capabilities and sec_ctx.capabilities.drop and
                        ('ALL' in sec_ctx.capabilities.drop or 'all' in sec_ctx.capabilities.drop)
                    )
                    if not caps_dropped_all:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Security",
                            "title": f"Capabilities not dropped: {container_name}",
                            "description": f"Container '{container_name}' does not drop all capabilities. Containers inherit default capabilities that may not be needed.",
                            "remediation": "Add 'drop: [\"ALL\"]' to capabilities and only add back specific needed capabilities.",
                            "timestamp": timestamp
                        })

                    # Check for running as root user (Restricted)
                    run_as_non_root = sec_ctx and sec_ctx.run_as_non_root
                    explicit_root = sec_ctx and sec_ctx.run_as_user == 0
                    pod_run_as_non_root = pod.spec.security_context and pod.spec.security_context.run_as_non_root

                    if explicit_root:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "high",
                            "category": "Security",
                            "title": f"Container runs as root (UID 0): {container_name}",
                            "description": f"Container '{container_name}' explicitly sets runAsUser: 0 (root). Running as root increases the impact of container escape.",
                            "remediation": "Set 'runAsUser' to a non-zero UID (e.g., 1000) and 'runAsNonRoot: true'.",
                            "timestamp": timestamp
                        })
                    elif not run_as_non_root and not pod_run_as_non_root:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Security",
                            "title": f"Container may run as root: {container_name}",
                            "description": f"Container '{container_name}' does not explicitly prevent running as root user.",
                            "remediation": "Set 'runAsNonRoot: true' in the container's or pod's securityContext.",
                            "timestamp": timestamp
                        })

                    # Check for writable root filesystem - NEW
                    if not sec_ctx or not sec_ctx.read_only_root_filesystem:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Security",
                            "title": f"Writable root filesystem: {container_name}",
                            "description": f"Container '{container_name}' has a writable root filesystem, which allows attackers to modify binaries or add malicious files.",
                            "remediation": "Set 'readOnlyRootFilesystem: true' and use emptyDir or volumes for writable paths.",
                            "timestamp": timestamp
                        })

                    # Check for missing resource limits
                    if not container.resources or not container.resources.limits:
                        await self.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Best Practice",
                            "title": f"Missing resource limits: {container_name}",
                            "description": f"Container '{container_name}' does not have resource limits defined, which can lead to resource exhaustion and DoS.",
                            "remediation": "Add resource limits (cpu and memory) to the container specification.",
                            "timestamp": timestamp
                        })

                    # Check for host ports - NEW
                    if container.ports:
                        for port in container.ports:
                            if port.host_port:
                                await self.report_finding({
                                    "resource_type": "Pod",
                                    "resource_name": pod_name,
                                    "namespace": namespace,
                                    "severity": "medium",
                                    "category": "Security",
                                    "title": f"Host port exposed: {port.host_port}",
                                    "description": f"Container '{container_name}' exposes host port {port.host_port}. This bypasses Kubernetes networking and may expose the service on all nodes.",
                                    "remediation": "Use Services (ClusterIP, NodePort, LoadBalancer) instead of hostPort for external access.",
                                    "timestamp": timestamp
                                })

                    # Check for secrets in environment variables - NEW (NSA/CISA)
                    if container.env:
                        for env in container.env:
                            if env.value_from and env.value_from.secret_key_ref:
                                await self.report_finding({
                                    "resource_type": "Pod",
                                    "resource_name": pod_name,
                                    "namespace": namespace,
                                    "severity": "low",
                                    "category": "Best Practice",
                                    "title": f"Secret exposed as environment variable: {env.name}",
                                    "description": f"Container '{container_name}' exposes secret '{env.value_from.secret_key_ref.name}' as environment variable '{env.name}'. Env vars can be leaked in logs, error messages, or child processes.",
                                    "remediation": "Mount secrets as files using volumes instead of environment variables.",
                                    "timestamp": timestamp
                                })

            logger.info("Pod security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning pods: {e}")
        except Exception as e:
            logger.error(f"Error scanning pods: {e}")

    async def scan_deployments(self):
        """Scan deployments for security issues"""
        logger.info("Scanning deployments for security issues...")
        try:
            deployments = self.apps_v1.list_deployment_for_all_namespaces()

            for deployment in deployments.items:
                if deployment.metadata.namespace in ['kube-system', 'kube-public', 'kube-node-lease']:
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"

                # Check for missing replica count
                if deployment.spec.replicas and deployment.spec.replicas < 2:
                    await self.report_finding({
                        "resource_type": "Deployment",
                        "resource_name": deployment.metadata.name,
                        "namespace": deployment.metadata.namespace,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": "Single replica deployment",
                        "description": f"Deployment has only {deployment.spec.replicas} replica(s), which affects high availability.",
                        "remediation": "Increase the number of replicas to at least 2 for production workloads.",
                        "timestamp": timestamp
                    })

            logger.info("Deployment security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning deployments: {e}")
        except Exception as e:
            logger.error(f"Error scanning deployments: {e}")

    async def scan_services(self):
        """Scan services for security issues"""
        logger.info("Scanning services for security issues...")
        try:
            services = self.v1.list_service_for_all_namespaces()

            for service in services.items:
                if service.metadata.namespace in ['kube-system', 'kube-public', 'kube-node-lease']:
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"
                service_name = service.metadata.name
                namespace = service.metadata.namespace

                # Check for LoadBalancer services
                if service.spec.type == "LoadBalancer":
                    await self.report_finding({
                        "resource_type": "Service",
                        "resource_name": service_name,
                        "namespace": namespace,
                        "severity": "medium",
                        "category": "Security",
                        "title": "Service exposed via LoadBalancer",
                        "description": "Service is exposed externally via LoadBalancer, which may be accessible from the internet.",
                        "remediation": "Review if external exposure is necessary. Consider using ClusterIP with Ingress controller for better control.",
                        "timestamp": timestamp
                    })

                # Check for NodePort services - NEW
                if service.spec.type == "NodePort":
                    await self.report_finding({
                        "resource_type": "Service",
                        "resource_name": service_name,
                        "namespace": namespace,
                        "severity": "medium",
                        "category": "Security",
                        "title": "Service exposed via NodePort",
                        "description": f"Service is exposed on all cluster nodes via NodePort. This exposes the service on every node's IP address.",
                        "remediation": "Consider using ClusterIP with Ingress controller for controlled external access, or LoadBalancer for cloud environments.",
                        "timestamp": timestamp
                    })

                # Check for ExternalName services - NEW
                if service.spec.type == "ExternalName":
                    await self.report_finding({
                        "resource_type": "Service",
                        "resource_name": service_name,
                        "namespace": namespace,
                        "severity": "low",
                        "category": "Security",
                        "title": "ExternalName service detected",
                        "description": f"Service redirects to external DNS name '{service.spec.external_name}'. This can be used for DNS rebinding attacks or unintended external access.",
                        "remediation": "Verify the external name is trusted and consider using NetworkPolicies to restrict egress traffic.",
                        "timestamp": timestamp
                    })

            logger.info("Service security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning services: {e}")
        except Exception as e:
            logger.error(f"Error scanning services: {e}")

    async def scan_rbac(self):
        """Scan RBAC for security issues"""
        logger.info("Scanning RBAC for security issues...")
        try:
            # Check ClusterRoles for overly permissive permissions
            cluster_roles = self.rbac_v1.list_cluster_role()

            for role in cluster_roles.items:
                if role.metadata.name.startswith('system:'):
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"
                role_name = role.metadata.name
                reported_wildcards = False

                if role.rules:
                    for rule in role.rules:
                        resources = rule.resources or []
                        verbs = rule.verbs or []
                        api_groups = rule.api_groups or []

                        # Check for wildcard resource permissions
                        if '*' in resources and not reported_wildcards:
                            await self.report_finding({
                                "resource_type": "ClusterRole",
                                "resource_name": role_name,
                                "namespace": "cluster-wide",
                                "severity": "high",
                                "category": "Security",
                                "title": "ClusterRole with wildcard resource permissions",
                                "description": f"ClusterRole '{role_name}' has wildcard (*) resource permissions, which grants access to all resources.",
                                "remediation": "Restrict permissions to specific resources instead of using wildcards.",
                                "timestamp": timestamp
                            })
                            reported_wildcards = True

                        # Check for wildcard verb permissions
                        if '*' in verbs and not reported_wildcards:
                            await self.report_finding({
                                "resource_type": "ClusterRole",
                                "resource_name": role_name,
                                "namespace": "cluster-wide",
                                "severity": "high",
                                "category": "Security",
                                "title": "ClusterRole with wildcard verb permissions",
                                "description": f"ClusterRole '{role_name}' has wildcard (*) verb permissions, which grants all actions.",
                                "remediation": "Restrict permissions to specific verbs (get, list, watch, create, update, delete) instead of using wildcards.",
                                "timestamp": timestamp
                            })
                            reported_wildcards = True

                        # Check for secrets access - NEW (NSA/CISA)
                        if 'secrets' in resources:
                            dangerous_verbs = [v for v in verbs if v in ['get', 'list', 'watch', '*']]
                            if dangerous_verbs:
                                await self.report_finding({
                                    "resource_type": "ClusterRole",
                                    "resource_name": role_name,
                                    "namespace": "cluster-wide",
                                    "severity": "high",
                                    "category": "Security",
                                    "title": f"ClusterRole can read secrets",
                                    "description": f"ClusterRole '{role_name}' has {', '.join(dangerous_verbs)} access to secrets. This allows reading sensitive data like passwords, tokens, and keys.",
                                    "remediation": "Restrict secrets access to only the namespaces and specific secrets required.",
                                    "timestamp": timestamp
                                })

                        # Check for pod exec permissions - NEW (NSA/CISA)
                        if 'pods/exec' in resources or ('pods' in resources and 'create' in verbs):
                            await self.report_finding({
                                "resource_type": "ClusterRole",
                                "resource_name": role_name,
                                "namespace": "cluster-wide",
                                "severity": "high",
                                "category": "Security",
                                "title": f"ClusterRole allows pod exec",
                                "description": f"ClusterRole '{role_name}' can execute commands inside pods. This allows running arbitrary commands in containers.",
                                "remediation": "Limit exec permissions to specific namespaces or remove if not needed for debugging.",
                                "timestamp": timestamp
                            })

                        # Check for cluster-admin equivalent - NEW
                        if '*' in resources and '*' in verbs and ('' in api_groups or '*' in api_groups):
                            await self.report_finding({
                                "resource_type": "ClusterRole",
                                "resource_name": role_name,
                                "namespace": "cluster-wide",
                                "severity": "critical",
                                "category": "Security",
                                "title": f"ClusterRole has cluster-admin equivalent permissions",
                                "description": f"ClusterRole '{role_name}' has full access to all resources in all API groups. This is equivalent to cluster-admin.",
                                "remediation": "Review if full cluster access is necessary. Apply principle of least privilege.",
                                "timestamp": timestamp
                            })

            # Also check namespaced Roles for dangerous permissions - NEW
            roles = self.rbac_v1.list_role_for_all_namespaces()
            for role in roles.items:
                if role.metadata.namespace in ['kube-system', 'kube-public', 'kube-node-lease']:
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"
                role_name = role.metadata.name
                namespace = role.metadata.namespace

                if role.rules:
                    for rule in role.rules:
                        resources = rule.resources or []
                        verbs = rule.verbs or []

                        # Check for secrets access in namespaced roles
                        if 'secrets' in resources:
                            dangerous_verbs = [v for v in verbs if v in ['get', 'list', 'watch', '*']]
                            if dangerous_verbs:
                                await self.report_finding({
                                    "resource_type": "Role",
                                    "resource_name": role_name,
                                    "namespace": namespace,
                                    "severity": "medium",
                                    "category": "Security",
                                    "title": f"Role can read secrets in namespace",
                                    "description": f"Role '{role_name}' has {', '.join(dangerous_verbs)} access to secrets in namespace '{namespace}'.",
                                    "remediation": "Review if secrets access is necessary and limit to specific secret names if possible.",
                                    "timestamp": timestamp
                                })

            logger.info("RBAC security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning RBAC: {e}")
        except Exception as e:
            logger.error(f"Error scanning RBAC: {e}")

    async def scan_network_policies(self):
        """Scan for missing network policies (NSA/CISA recommendation)"""
        logger.info("Scanning network policies...")
        try:
            # Get all namespaces
            namespaces = self.v1.list_namespace()

            # Get all network policies
            network_policies = self.networking_v1.list_network_policy_for_all_namespaces()

            # Build a set of namespaces that have at least one NetworkPolicy
            namespaces_with_policies = set()
            for policy in network_policies.items:
                namespaces_with_policies.add(policy.metadata.namespace)

            timestamp = datetime.utcnow().isoformat() + "Z"

            for ns in namespaces.items:
                ns_name = ns.metadata.name

                # Skip system namespaces
                if ns_name in ['kube-system', 'kube-public', 'kube-node-lease', 'kube-flannel']:
                    continue

                # Check if namespace has any pods (skip empty namespaces)
                pods = self.v1.list_namespaced_pod(ns_name)
                if not pods.items:
                    continue

                # Report if namespace has no network policies
                if ns_name not in namespaces_with_policies:
                    await self.report_finding({
                        "resource_type": "Namespace",
                        "resource_name": ns_name,
                        "namespace": ns_name,
                        "severity": "medium",
                        "category": "Security",
                        "title": "Namespace has no NetworkPolicy",
                        "description": f"Namespace '{ns_name}' has no NetworkPolicy defined. All pods can communicate with all other pods in the cluster without restriction.",
                        "remediation": "Create NetworkPolicies to implement network segmentation and restrict pod-to-pod communication based on the principle of least privilege.",
                        "timestamp": timestamp
                    })

            logger.info("Network policy scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning network policies: {e}")
        except Exception as e:
            logger.error(f"Error scanning network policies: {e}")

    async def scan_service_accounts(self):
        """Scan service accounts for security issues"""
        logger.info("Scanning service accounts...")
        try:
            # Get all pods to check their service account usage
            pods = self.v1.list_pod_for_all_namespaces()

            timestamp = datetime.utcnow().isoformat() + "Z"

            for pod in pods.items:
                if pod.metadata.namespace in ['kube-system', 'kube-public', 'kube-node-lease']:
                    continue

                pod_name = pod.metadata.name
                namespace = pod.metadata.namespace
                sa_name = pod.spec.service_account_name or 'default'

                # Check for default service account usage - NEW
                if sa_name == 'default':
                    await self.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": "Pod uses default ServiceAccount",
                        "description": f"Pod '{pod_name}' uses the default service account. This makes it harder to apply the principle of least privilege.",
                        "remediation": "Create a dedicated ServiceAccount for this workload and assign only the permissions it needs.",
                        "timestamp": timestamp
                    })

                # Check for automounted service account token - NEW (NSA/CISA)
                automount = pod.spec.automount_service_account_token
                if automount is None or automount:
                    # Check if the service account itself disables it
                    try:
                        sa = self.v1.read_namespaced_service_account(sa_name, namespace)
                        sa_automount = sa.automount_service_account_token
                        if sa_automount is None or sa_automount:
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod_name,
                                "namespace": namespace,
                                "severity": "medium",
                                "category": "Security",
                                "title": "ServiceAccount token auto-mounted",
                                "description": f"Pod '{pod_name}' has the ServiceAccount token automatically mounted. If compromised, this token can be used to access the Kubernetes API.",
                                "remediation": "Set 'automountServiceAccountToken: false' in the pod spec or service account if API access is not needed.",
                                "timestamp": timestamp
                            })
                    except ApiException:
                        pass  # Service account might not exist or we don't have permission

            logger.info("Service account scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning service accounts: {e}")
        except Exception as e:
            logger.error(f"Error scanning service accounts: {e}")

    async def report_finding(self, finding_data: dict):
        """Report a security finding to the backend"""
        await self.backend_client.report_security_finding(finding_data)