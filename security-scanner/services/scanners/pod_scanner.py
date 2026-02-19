import logging
from datetime import datetime
from typing import TYPE_CHECKING

from kubernetes.client.rest import ApiException

from services.scanner_base import (
    DANGEROUS_CAPABILITIES, TRUSTED_REGISTRIES, LARGE_EMPTYDIR_THRESHOLD,
    get_image_registry, parse_size_to_bytes,
)

if TYPE_CHECKING:
    from services.security_scanner import SecurityScanner

logger = logging.getLogger(__name__)


class PodScanner:
    """Pod-specific security scanning: single-pod checks, bulk scan, service accounts, seccomp."""

    def __init__(self, scanner: 'SecurityScanner'):
        self.scanner = scanner

    async def scan_single_pod(self, pod):
        """Scan a single pod for security issues (canonical implementation).

        Used by both real-time watch and initial bulk scan.
        Clears existing findings for the pod first, then runs all checks.
        """
        namespace = pod.metadata.namespace
        pod_name = pod.metadata.name
        timestamp = datetime.utcnow().isoformat() + "Z"
        self.scanner._set_resource_context(pod, 'v1', 'Pod')

        # Clear existing findings before re-scanning so fixed issues are removed
        await self.scanner.backend_client.delete_findings_by_resource("Pod", namespace, pod_name)

        logger.debug(f"Scanning pod: {namespace}/{pod_name}")

        # === Pod-level security checks ===

        if pod.spec.host_network:
            await self.scanner.report_finding({
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

        if pod.spec.host_pid:
            await self.scanner.report_finding({
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

        if pod.spec.host_ipc:
            await self.scanner.report_finding({
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

        # Check for hostPath volumes
        if pod.spec.volumes:
            for volume in pod.spec.volumes:
                if volume.host_path:
                    severity = "critical" if volume.host_path.path in ['/', '/etc', '/var', '/root', '/home'] else "high"
                    await self.scanner.report_finding({
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

            if sec_ctx and sec_ctx.privileged:
                await self.scanner.report_finding({
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

            if not sec_ctx or sec_ctx.allow_privilege_escalation is None or sec_ctx.allow_privilege_escalation:
                await self.scanner.report_finding({
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

            # Check for dangerous capabilities
            if sec_ctx and sec_ctx.capabilities and sec_ctx.capabilities.add:
                dangerous_caps = [cap for cap in sec_ctx.capabilities.add if cap in DANGEROUS_CAPABILITIES]
                if dangerous_caps:
                    await self.scanner.report_finding({
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

            # Check for missing capability drop ALL
            caps_dropped_all = (
                sec_ctx and sec_ctx.capabilities and sec_ctx.capabilities.drop and
                ('ALL' in sec_ctx.capabilities.drop or 'all' in sec_ctx.capabilities.drop)
            )
            if not caps_dropped_all:
                await self.scanner.report_finding({
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

            # Check for running as root
            run_as_non_root = sec_ctx and sec_ctx.run_as_non_root
            explicit_root = sec_ctx and sec_ctx.run_as_user == 0
            pod_run_as_non_root = pod.spec.security_context and pod.spec.security_context.run_as_non_root

            if explicit_root:
                await self.scanner.report_finding({
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
                await self.scanner.report_finding({
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

            # Check for writable root filesystem
            if not sec_ctx or not sec_ctx.read_only_root_filesystem:
                await self.scanner.report_finding({
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
                await self.scanner.report_finding({
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

            # Check for host ports
            if container.ports:
                for port in container.ports:
                    if port.host_port:
                        await self.scanner.report_finding({
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

            # Check for secrets in environment variables
            if container.env:
                for env in container.env:
                    if env.value_from and env.value_from.secret_key_ref:
                        await self.scanner.report_finding({
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

            # Check for :latest image tag
            image = container.image or ""
            if image.endswith(':latest') or (':' not in image.split('/')[-1]):
                await self.scanner.report_finding({
                    "resource_type": "Pod",
                    "resource_name": pod_name,
                    "namespace": namespace,
                    "severity": "medium",
                    "category": "Best Practice",
                    "title": f"Image uses :latest or no tag: {container_name}",
                    "description": f"Container '{container_name}' uses image '{image}' with :latest or no tag. Mutable tags can introduce unexpected changes and make rollbacks difficult.",
                    "remediation": "Use immutable image tags (e.g., specific versions or SHA digests) for reproducible deployments.",
                    "timestamp": timestamp
                })

            # Check for untrusted registry
            image_registry = get_image_registry(image)
            await self.scanner.exclusion_mgr.refresh_trusted_registries()
            if image_registry and image_registry not in TRUSTED_REGISTRIES and image_registry not in self.scanner.exclusion_mgr.admin_trusted_registries:
                await self.scanner.report_finding({
                    "resource_type": "Pod",
                    "resource_name": pod_name,
                    "namespace": namespace,
                    "severity": "high",
                    "category": "Security",
                    "title": f"Image from untrusted registry: {container_name}",
                    "description": f"Container '{container_name}' uses image from registry '{image_registry}' which is not in the trusted registry list.",
                    "remediation": f"Use images from trusted registries: {', '.join(TRUSTED_REGISTRIES[:4])}. Or add the registry to the trusted list via the Admin panel.",
                    "timestamp": timestamp
                })

            # Check for missing imagePullPolicy with mutable tag
            if not container.image_pull_policy or container.image_pull_policy == "IfNotPresent":
                if image.endswith(':latest') or (':' not in image.split('/')[-1]):
                    await self.scanner.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": f"Missing imagePullPolicy with mutable tag: {container_name}",
                        "description": f"Container '{container_name}' uses a mutable image tag without imagePullPolicy: Always. Cached vulnerable images may be used.",
                        "remediation": "Set imagePullPolicy: Always when using mutable tags, or use immutable image tags.",
                        "timestamp": timestamp
                    })

        # Check for emptyDir volumes with large sizeLimit
        if pod.spec.volumes:
            for volume in pod.spec.volumes:
                if volume.empty_dir and volume.empty_dir.size_limit:
                    size_limit_str = volume.empty_dir.size_limit
                    size_bytes = parse_size_to_bytes(size_limit_str)
                    if size_bytes and size_bytes > LARGE_EMPTYDIR_THRESHOLD:
                        await self.scanner.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "low",
                            "category": "Best Practice",
                            "title": f"EmptyDir with large sizeLimit: {volume.name}",
                            "description": f"Volume '{volume.name}' has emptyDir with sizeLimit of {size_limit_str}. Large emptyDir volumes can exhaust node disk space.",
                            "remediation": "Consider using PersistentVolumes for large storage needs, or reduce the sizeLimit.",
                            "timestamp": timestamp
                        })

        # Check for AppArmor profile
        annotations = pod.metadata.annotations or {}
        for container in all_containers:
            container_name = container.name
            apparmor_key = f"container.apparmor.security.beta.kubernetes.io/{container_name}"
            if apparmor_key not in annotations:
                await self.scanner.report_finding({
                    "resource_type": "Pod",
                    "resource_name": pod_name,
                    "namespace": namespace,
                    "severity": "medium",
                    "category": "Security",
                    "title": f"Missing AppArmor profile: {container_name}",
                    "description": f"Container '{container_name}' does not have an AppArmor profile configured. AppArmor provides mandatory access control for Linux applications.",
                    "remediation": f"Add annotation '{apparmor_key}: runtime/default' to use the default AppArmor profile.",
                    "timestamp": timestamp
                })

        # Check for SELinux options
        pod_sec_ctx = pod.spec.security_context
        pod_has_selinux = pod_sec_ctx and pod_sec_ctx.se_linux_options
        for container in all_containers:
            container_name = container.name
            sec_ctx = container.security_context
            container_has_selinux = sec_ctx and sec_ctx.se_linux_options
            if not pod_has_selinux and not container_has_selinux:
                await self.scanner.report_finding({
                    "resource_type": "Pod",
                    "resource_name": pod_name,
                    "namespace": namespace,
                    "severity": "medium",
                    "category": "Security",
                    "title": f"Missing SELinux options: {container_name}",
                    "description": f"Container '{container_name}' does not have SELinux options configured. SELinux provides mandatory access control enforcement.",
                    "remediation": "Configure seLinuxOptions in the pod or container securityContext if running on SELinux-enabled nodes.",
                    "timestamp": timestamp
                })

    async def scan_pods(self):
        """Scan all pods for security issues. Delegates to scan_single_pod."""
        logger.info("Scanning pods for security issues...")
        try:
            pods = self.scanner.v1.list_pod_for_all_namespaces()

            for pod in pods.items:
                if self.scanner.exclusion_mgr.is_namespace_excluded(pod.metadata.namespace):
                    continue
                await self.scan_single_pod(pod)

            logger.info("Pod security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning pods: {e}")
        except Exception as e:
            logger.error(f"Error scanning pods: {e}")

    async def scan_service_accounts(self):
        """Scan service accounts for security issues"""
        logger.info("Scanning service accounts...")
        try:
            pods = self.scanner.v1.list_pod_for_all_namespaces()
            timestamp = datetime.utcnow().isoformat() + "Z"

            for pod in pods.items:
                if self.scanner.exclusion_mgr.is_namespace_excluded(pod.metadata.namespace):
                    continue

                pod_name = pod.metadata.name
                namespace = pod.metadata.namespace
                sa_name = pod.spec.service_account_name or 'default'
                self.scanner._set_resource_context(pod, 'v1', 'Pod')

                if sa_name == 'default':
                    await self.scanner.report_finding({
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

                automount = pod.spec.automount_service_account_token
                if automount is None or automount:
                    try:
                        sa = self.scanner.v1.read_namespaced_service_account(sa_name, namespace)
                        sa_automount = sa.automount_service_account_token
                        if sa_automount is None or sa_automount:
                            await self.scanner.report_finding({
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
                        pass

                sa_namespace = namespace
                if '/' in sa_name:
                    sa_namespace, sa_name = sa_name.split('/', 1)

                if sa_namespace == 'kube-system' or (namespace != 'kube-system' and sa_name.startswith('system:')):
                    await self.scanner.report_finding({
                        "resource_type": "Pod",
                        "resource_name": pod_name,
                        "namespace": namespace,
                        "severity": "medium",
                        "category": "Security",
                        "title": f"Pod uses system ServiceAccount: {sa_name}",
                        "description": f"Pod '{pod_name}' uses a system-level ServiceAccount. This could grant unintended elevated permissions.",
                        "remediation": "Create a dedicated ServiceAccount in the workload's namespace with only required permissions.",
                        "timestamp": timestamp
                    })

            logger.info("Service account scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning service accounts: {e}")
        except Exception as e:
            logger.error(f"Error scanning service accounts: {e}")

    async def scan_seccomp_profiles(self):
        """Scan pods for missing seccomp profiles (PSS Restricted requirement)"""
        logger.info("Scanning seccomp profiles...")
        try:
            pods = self.scanner.v1.list_pod_for_all_namespaces()
            timestamp = datetime.utcnow().isoformat() + "Z"

            for pod in pods.items:
                if self.scanner.exclusion_mgr.is_namespace_excluded(pod.metadata.namespace):
                    continue

                pod_name = pod.metadata.name
                namespace = pod.metadata.namespace
                self.scanner._set_resource_context(pod, 'v1', 'Pod')

                pod_sec_ctx = pod.spec.security_context
                pod_has_seccomp = (
                    pod_sec_ctx and pod_sec_ctx.seccomp_profile and
                    pod_sec_ctx.seccomp_profile.type in ['RuntimeDefault', 'Localhost']
                )

                all_containers = (pod.spec.containers or []) + (pod.spec.init_containers or [])

                for container in all_containers:
                    container_name = container.name
                    sec_ctx = container.security_context

                    container_has_seccomp = (
                        sec_ctx and sec_ctx.seccomp_profile and
                        sec_ctx.seccomp_profile.type in ['RuntimeDefault', 'Localhost']
                    )

                    if not pod_has_seccomp and not container_has_seccomp:
                        await self.scanner.report_finding({
                            "resource_type": "Pod",
                            "resource_name": pod_name,
                            "namespace": namespace,
                            "severity": "medium",
                            "category": "Security",
                            "title": f"Missing seccomp profile: {container_name}",
                            "description": f"Container '{container_name}' does not have a seccomp profile configured. Seccomp restricts which system calls a container can make.",
                            "remediation": "Set seccompProfile.type to 'RuntimeDefault' in the pod or container securityContext. This is required for PSS Restricted compliance.",
                            "timestamp": timestamp
                        })

            logger.info("Seccomp profile scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning seccomp profiles: {e}")
        except Exception as e:
            logger.error(f"Error scanning seccomp profiles: {e}")
