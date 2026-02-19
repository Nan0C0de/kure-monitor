import re
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from kubernetes.client.rest import ApiException

if TYPE_CHECKING:
    from services.security_scanner import SecurityScanner

logger = logging.getLogger(__name__)


class ResourceScanner:
    """Non-pod security scanners: deployments, services, RBAC, network policies, etc."""

    def __init__(self, scanner: 'SecurityScanner'):
        self.scanner = scanner

    # --- Single-resource scanners (used by real-time watches) ---

    async def scan_single_deployment(self, deployment):
        """Scan a single deployment for security issues"""
        namespace = deployment.metadata.namespace
        deploy_name = deployment.metadata.name
        timestamp = datetime.utcnow().isoformat() + "Z"
        self.scanner._set_resource_context(deployment, 'apps/v1', 'Deployment')

        await self.scanner.backend_client.delete_findings_by_resource("Deployment", namespace, deploy_name)
        logger.debug(f"Real-time scanning deployment: {namespace}/{deploy_name}")

        if deployment.spec.replicas and deployment.spec.replicas < 2:
            await self.scanner.report_finding({
                "resource_type": "Deployment",
                "resource_name": deploy_name,
                "namespace": namespace,
                "severity": "low",
                "category": "Best Practice",
                "title": "Single replica deployment",
                "description": f"Deployment has only {deployment.spec.replicas} replica(s), which affects high availability.",
                "remediation": "Increase the number of replicas to at least 2 for production workloads.",
                "timestamp": timestamp
            })

        replicas = deployment.spec.replicas or 1
        if replicas >= 2:
            pod_template = deployment.spec.template
            affinity = pod_template.spec.affinity if pod_template.spec else None
            has_anti_affinity = (
                affinity and affinity.pod_anti_affinity and
                (affinity.pod_anti_affinity.required_during_scheduling_ignored_during_execution or
                 affinity.pod_anti_affinity.preferred_during_scheduling_ignored_during_execution)
            )
            if not has_anti_affinity:
                await self.scanner.report_finding({
                    "resource_type": "Deployment",
                    "resource_name": deploy_name,
                    "namespace": namespace,
                    "severity": "low",
                    "category": "Best Practice",
                    "title": "HA deployment without pod anti-affinity",
                    "description": f"Deployment '{deploy_name}' has {replicas} replicas but no pod anti-affinity rules. All replicas could be scheduled on the same node.",
                    "remediation": "Add podAntiAffinity rules to spread replicas across nodes for better fault tolerance.",
                    "timestamp": timestamp
                })

    async def scan_single_service(self, service):
        """Scan a single service for security issues"""
        namespace = service.metadata.namespace
        service_name = service.metadata.name
        timestamp = datetime.utcnow().isoformat() + "Z"
        self.scanner._set_resource_context(service, 'v1', 'Service')

        await self.scanner.backend_client.delete_findings_by_resource("Service", namespace, service_name)
        logger.debug(f"Real-time scanning service: {namespace}/{service_name}")

        if service.spec.type == "LoadBalancer":
            await self.scanner.report_finding({
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

        if service.spec.type == "NodePort":
            await self.scanner.report_finding({
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

        if service.spec.type == "ExternalName":
            await self.scanner.report_finding({
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

    async def scan_single_cluster_role(self, role):
        """Scan a single ClusterRole for security issues"""
        role_name = role.metadata.name
        timestamp = datetime.utcnow().isoformat() + "Z"
        self.scanner._set_resource_context(role, 'rbac.authorization.k8s.io/v1', 'ClusterRole')

        await self.scanner.backend_client.delete_findings_by_resource("ClusterRole", "cluster-wide", role_name)
        logger.debug(f"Real-time scanning ClusterRole: {role_name}")

        reported_wildcards = False
        if role.rules:
            for rule in role.rules:
                resources = rule.resources or []
                verbs = rule.verbs or []
                api_groups = rule.api_groups or []

                if '*' in resources and not reported_wildcards:
                    await self.scanner.report_finding({
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

                if '*' in verbs and not reported_wildcards:
                    await self.scanner.report_finding({
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

                if 'secrets' in resources:
                    dangerous_verbs = [v for v in verbs if v in ['get', 'list', 'watch', '*']]
                    if dangerous_verbs:
                        await self.scanner.report_finding({
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

                if 'pods/exec' in resources or ('pods' in resources and 'create' in verbs):
                    await self.scanner.report_finding({
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

                if '*' in resources and '*' in verbs and ('' in api_groups or '*' in api_groups):
                    await self.scanner.report_finding({
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

    async def scan_single_role(self, role):
        """Scan a single Role for security issues"""
        role_name = role.metadata.name
        namespace = role.metadata.namespace
        timestamp = datetime.utcnow().isoformat() + "Z"
        self.scanner._set_resource_context(role, 'rbac.authorization.k8s.io/v1', 'Role')

        await self.scanner.backend_client.delete_findings_by_resource("Role", namespace, role_name)
        logger.debug(f"Real-time scanning Role: {namespace}/{role_name}")

        if role.rules:
            for rule in role.rules:
                resources = rule.resources or []
                verbs = rule.verbs or []

                if 'secrets' in resources:
                    dangerous_verbs = [v for v in verbs if v in ['get', 'list', 'watch', '*']]
                    if dangerous_verbs:
                        await self.scanner.report_finding({
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

    async def scan_single_ingress(self, ingress):
        """Scan a single Ingress for security issues"""
        namespace = ingress.metadata.namespace
        ingress_name = ingress.metadata.name
        timestamp = datetime.utcnow().isoformat() + "Z"
        annotations = ingress.metadata.annotations or {}
        self.scanner._set_resource_context(ingress, 'networking.k8s.io/v1', 'Ingress')

        await self.scanner.backend_client.delete_findings_by_resource("Ingress", namespace, ingress_name)
        logger.debug(f"Real-time scanning ingress: {namespace}/{ingress_name}")

        dangerous_annotations = [
            'nginx.ingress.kubernetes.io/ssl-passthrough',
            'nginx.ingress.kubernetes.io/backend-protocol',
            'nginx.ingress.kubernetes.io/configuration-snippet',
            'nginx.ingress.kubernetes.io/server-snippet',
        ]

        if not ingress.spec.tls:
            await self.scanner.report_finding({
                "resource_type": "Ingress",
                "resource_name": ingress_name,
                "namespace": namespace,
                "severity": "high",
                "category": "Security",
                "title": "Ingress without TLS configuration",
                "description": f"Ingress '{ingress_name}' does not have TLS configured. Traffic will be unencrypted.",
                "remediation": "Configure TLS for the Ingress using a certificate from cert-manager or a manually provisioned certificate.",
                "timestamp": timestamp
            })

        if ingress.spec.rules:
            for rule in ingress.spec.rules:
                if rule.host and rule.host.startswith('*'):
                    await self.scanner.report_finding({
                        "resource_type": "Ingress",
                        "resource_name": ingress_name,
                        "namespace": namespace,
                        "severity": "medium",
                        "category": "Security",
                        "title": f"Ingress with wildcard host: {rule.host}",
                        "description": f"Ingress '{ingress_name}' uses wildcard host '{rule.host}'. This could expose services to unintended subdomains.",
                        "remediation": "Use specific hostnames instead of wildcards to limit exposure.",
                        "timestamp": timestamp
                    })

        for annotation in dangerous_annotations:
            if annotation in annotations:
                await self.scanner.report_finding({
                    "resource_type": "Ingress",
                    "resource_name": ingress_name,
                    "namespace": namespace,
                    "severity": "medium",
                    "category": "Security",
                    "title": f"Potentially dangerous Ingress annotation",
                    "description": f"Ingress '{ingress_name}' uses annotation '{annotation}' which could be used to bypass security controls or inject configuration.",
                    "remediation": "Review if this annotation is necessary and ensure it doesn't introduce security vulnerabilities.",
                    "timestamp": timestamp
                })

    async def scan_single_cronjob(self, cronjob):
        """Scan a single CronJob for security issues"""
        namespace = cronjob.metadata.namespace
        cj_name = cronjob.metadata.name
        timestamp = datetime.utcnow().isoformat() + "Z"
        self.scanner._set_resource_context(cronjob, 'batch/v1', 'CronJob')

        await self.scanner.backend_client.delete_findings_by_resource("CronJob", namespace, cj_name)
        logger.debug(f"Real-time scanning cronjob: {namespace}/{cj_name}")

        job_template = cronjob.spec.job_template.spec.template.spec

        success_limit = cronjob.spec.successful_jobs_history_limit
        if success_limit and success_limit > 10:
            await self.scanner.report_finding({
                "resource_type": "CronJob",
                "resource_name": cj_name,
                "namespace": namespace,
                "severity": "low",
                "category": "Best Practice",
                "title": "CronJob retains excessive job history",
                "description": f"CronJob '{cj_name}' retains {success_limit} successful jobs. This can consume significant cluster resources over time.",
                "remediation": "Set successfulJobsHistoryLimit to a lower value (e.g., 3) to reduce resource consumption.",
                "timestamp": timestamp
            })

        all_containers = (job_template.containers or []) + (job_template.init_containers or [])

        for container in all_containers:
            sec_ctx = container.security_context

            if sec_ctx and sec_ctx.privileged:
                await self.scanner.report_finding({
                    "resource_type": "CronJob",
                    "resource_name": cj_name,
                    "namespace": namespace,
                    "severity": "critical",
                    "category": "Security",
                    "title": f"CronJob runs privileged container: {container.name}",
                    "description": f"CronJob '{cj_name}' creates jobs with privileged container '{container.name}'. Privileged jobs that run on schedule pose significant security risks.",
                    "remediation": "Remove 'privileged: true' from the container's securityContext. Use specific capabilities if elevated permissions are required.",
                    "timestamp": timestamp
                })

            if job_template.host_network:
                await self.scanner.report_finding({
                    "resource_type": "CronJob",
                    "resource_name": cj_name,
                    "namespace": namespace,
                    "severity": "high",
                    "category": "Security",
                    "title": "CronJob uses host network",
                    "description": f"CronJob '{cj_name}' creates jobs with hostNetwork access, which bypasses network policies.",
                    "remediation": "Remove 'hostNetwork: true' unless the job specifically requires host network access.",
                    "timestamp": timestamp
                })
                break  # Only report once per CronJob

    # --- Bulk scan methods (used by initial scan_cluster) ---

    async def scan_deployments(self):
        """Scan all deployments for security issues"""
        logger.info("Scanning deployments for security issues...")
        try:
            deployments = self.scanner.apps_v1.list_deployment_for_all_namespaces()
            for deployment in deployments.items:
                if self.scanner.exclusion_mgr.is_namespace_excluded(deployment.metadata.namespace):
                    continue
                await self.scan_single_deployment(deployment)
            logger.info("Deployment security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning deployments: {e}")
        except Exception as e:
            logger.error(f"Error scanning deployments: {e}")

    async def scan_services(self):
        """Scan all services for security issues"""
        logger.info("Scanning services for security issues...")
        try:
            services = self.scanner.v1.list_service_for_all_namespaces()
            for service in services.items:
                if self.scanner.exclusion_mgr.is_namespace_excluded(service.metadata.namespace):
                    continue
                await self.scan_single_service(service)
            logger.info("Service security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning services: {e}")
        except Exception as e:
            logger.error(f"Error scanning services: {e}")

    async def scan_rbac(self):
        """Scan RBAC for security issues"""
        logger.info("Scanning RBAC for security issues...")
        try:
            cluster_roles = self.scanner.rbac_v1.list_cluster_role()
            for role in cluster_roles.items:
                if role.metadata.name.startswith('system:'):
                    continue
                await self.scan_single_cluster_role(role)

            roles = self.scanner.rbac_v1.list_role_for_all_namespaces()
            for role in roles.items:
                if self.scanner.exclusion_mgr.is_namespace_excluded(role.metadata.namespace):
                    continue
                await self.scan_single_role(role)

            logger.info("RBAC security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning RBAC: {e}")
        except Exception as e:
            logger.error(f"Error scanning RBAC: {e}")

    async def scan_network_policies(self):
        """Scan for missing network policies"""
        logger.info("Scanning network policies...")
        try:
            namespaces = self.scanner.v1.list_namespace()
            network_policies = self.scanner.networking_v1.list_network_policy_for_all_namespaces()

            namespaces_with_policies = set()
            for policy in network_policies.items:
                namespaces_with_policies.add(policy.metadata.namespace)

            timestamp = datetime.utcnow().isoformat() + "Z"

            for ns in namespaces.items:
                ns_name = ns.metadata.name
                if self.scanner.exclusion_mgr.is_namespace_excluded(ns_name):
                    continue

                pods = self.scanner.v1.list_namespaced_pod(ns_name)
                if not pods.items:
                    continue

                self.scanner._set_resource_context(ns, 'v1', 'Namespace')

                if ns_name not in namespaces_with_policies:
                    await self.scanner.report_finding({
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

    async def scan_pod_security_admission(self):
        """Scan namespaces for Pod Security Admission (PSA) labels"""
        logger.info("Scanning Pod Security Admission labels...")
        try:
            namespaces = self.scanner.v1.list_namespace()
            timestamp = datetime.utcnow().isoformat() + "Z"

            for ns in namespaces.items:
                ns_name = ns.metadata.name
                if self.scanner.exclusion_mgr.is_namespace_excluded(ns_name):
                    continue

                labels = ns.metadata.labels or {}
                self.scanner._set_resource_context(ns, 'v1', 'Namespace')

                enforce_label = labels.get('pod-security.kubernetes.io/enforce')
                warn_label = labels.get('pod-security.kubernetes.io/warn')
                audit_label = labels.get('pod-security.kubernetes.io/audit')

                pods = self.scanner.v1.list_namespaced_pod(ns_name)
                if not pods.items:
                    continue

                if not enforce_label and not warn_label and not audit_label:
                    await self.scanner.report_finding({
                        "resource_type": "Namespace",
                        "resource_name": ns_name,
                        "namespace": ns_name,
                        "severity": "medium",
                        "category": "Compliance",
                        "title": "No Pod Security Admission labels configured",
                        "description": f"Namespace '{ns_name}' has no Pod Security Admission labels configured. PSA provides built-in enforcement of Pod Security Standards.",
                        "remediation": "Add PSA labels to the namespace: 'pod-security.kubernetes.io/enforce: baseline' or 'restricted' for production workloads.",
                        "timestamp": timestamp
                    })
                elif enforce_label == 'privileged':
                    await self.scanner.report_finding({
                        "resource_type": "Namespace",
                        "resource_name": ns_name,
                        "namespace": ns_name,
                        "severity": "high",
                        "category": "Security",
                        "title": "Pod Security Admission set to privileged",
                        "description": f"Namespace '{ns_name}' has PSA enforce set to 'privileged', which allows unrestricted pod configurations including privileged containers.",
                        "remediation": "Consider using 'baseline' or 'restricted' enforce level for better security. Use 'privileged' only for system namespaces.",
                        "timestamp": timestamp
                    })

            logger.info("Pod Security Admission scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning PSA: {e}")
        except Exception as e:
            logger.error(f"Error scanning PSA: {e}")

    async def scan_ingresses(self):
        """Scan all Ingress resources for security issues"""
        logger.info("Scanning Ingresses for security issues...")
        try:
            ingresses = self.scanner.networking_v1.list_ingress_for_all_namespaces()
            for ingress in ingresses.items:
                if self.scanner.exclusion_mgr.is_namespace_excluded(ingress.metadata.namespace):
                    continue
                await self.scan_single_ingress(ingress)
            logger.info("Ingress security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning Ingresses: {e}")
        except Exception as e:
            logger.error(f"Error scanning Ingresses: {e}")

    async def scan_cluster_role_bindings(self):
        """Scan ClusterRoleBindings for security issues"""
        logger.info("Scanning ClusterRoleBindings...")
        try:
            bindings = self.scanner.rbac_v1.list_cluster_role_binding()
            timestamp = datetime.utcnow().isoformat() + "Z"

            dangerous_subjects = [
                ('Group', 'system:anonymous'),
                ('Group', 'system:unauthenticated'),
            ]
            high_privilege_roles = ['cluster-admin', 'admin', 'edit']

            for binding in bindings.items:
                if binding.metadata.name.startswith('system:'):
                    continue

                binding_name = binding.metadata.name
                role_ref = binding.role_ref.name if binding.role_ref else None
                subjects = binding.subjects or []
                self.scanner._set_resource_context(binding, 'rbac.authorization.k8s.io/v1', 'ClusterRoleBinding')

                for subject in subjects:
                    subject_key = (subject.kind, subject.name)
                    if subject_key in dangerous_subjects:
                        await self.scanner.report_finding({
                            "resource_type": "ClusterRoleBinding",
                            "resource_name": binding_name,
                            "namespace": "cluster-wide",
                            "severity": "critical",
                            "category": "Security",
                            "title": f"ClusterRoleBinding grants permissions to {subject.name}",
                            "description": f"ClusterRoleBinding '{binding_name}' grants cluster-wide permissions to '{subject.name}'. This allows unauthenticated access to cluster resources.",
                            "remediation": "Remove this binding or change the subject to authenticated users/groups only.",
                            "timestamp": timestamp
                        })

                if role_ref in high_privilege_roles:
                    for subject in subjects:
                        if subject.kind == 'ServiceAccount':
                            await self.scanner.report_finding({
                                "resource_type": "ClusterRoleBinding",
                                "resource_name": binding_name,
                                "namespace": "cluster-wide",
                                "severity": "high",
                                "category": "Security",
                                "title": f"ServiceAccount bound to {role_ref}",
                                "description": f"ServiceAccount '{subject.namespace}/{subject.name}' is bound to high-privilege ClusterRole '{role_ref}' via '{binding_name}'.",
                                "remediation": "Review if this ServiceAccount requires cluster-admin level access. Apply principle of least privilege.",
                                "timestamp": timestamp
                            })

            logger.info("ClusterRoleBinding scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning ClusterRoleBindings: {e}")
        except Exception as e:
            logger.error(f"Error scanning ClusterRoleBindings: {e}")

    async def scan_pod_disruption_budgets(self):
        """Scan for critical deployments without PodDisruptionBudgets"""
        logger.info("Scanning PodDisruptionBudgets...")
        try:
            deployments = self.scanner.apps_v1.list_deployment_for_all_namespaces()
            pdbs = self.scanner.policy_v1.list_pod_disruption_budget_for_all_namespaces()
            timestamp = datetime.utcnow().isoformat() + "Z"

            pdb_selectors = {}
            for pdb in pdbs.items:
                ns = pdb.metadata.namespace
                if ns not in pdb_selectors:
                    pdb_selectors[ns] = []
                if pdb.spec.selector and pdb.spec.selector.match_labels:
                    pdb_selectors[ns].append(pdb.spec.selector.match_labels)

            for deployment in deployments.items:
                if self.scanner.exclusion_mgr.is_namespace_excluded(deployment.metadata.namespace):
                    continue

                deploy_name = deployment.metadata.name
                namespace = deployment.metadata.namespace
                replicas = deployment.spec.replicas or 1

                if replicas < 2:
                    continue

                self.scanner._set_resource_context(deployment, 'apps/v1', 'Deployment')

                deploy_labels = deployment.spec.selector.match_labels or {}
                has_pdb = False

                if namespace in pdb_selectors:
                    for pdb_labels in pdb_selectors[namespace]:
                        if all(deploy_labels.get(k) == v for k, v in pdb_labels.items()):
                            has_pdb = True
                            break

                if not has_pdb:
                    await self.scanner.report_finding({
                        "resource_type": "Deployment",
                        "resource_name": deploy_name,
                        "namespace": namespace,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": "High-availability deployment without PodDisruptionBudget",
                        "description": f"Deployment '{deploy_name}' has {replicas} replicas but no PodDisruptionBudget. During cluster maintenance, all pods could be evicted simultaneously.",
                        "remediation": "Create a PodDisruptionBudget to ensure minimum availability during voluntary disruptions like node drains.",
                        "timestamp": timestamp
                    })

            logger.info("PodDisruptionBudget scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning PDBs: {e}")
        except Exception as e:
            logger.error(f"Error scanning PDBs: {e}")

    async def scan_resource_quotas(self):
        """Scan namespaces for missing ResourceQuotas and LimitRanges"""
        logger.info("Scanning ResourceQuotas and LimitRanges...")
        try:
            namespaces = self.scanner.v1.list_namespace()
            timestamp = datetime.utcnow().isoformat() + "Z"

            for ns in namespaces.items:
                ns_name = ns.metadata.name
                if self.scanner.exclusion_mgr.is_namespace_excluded(ns_name):
                    continue

                pods = self.scanner.v1.list_namespaced_pod(ns_name)
                if not pods.items:
                    continue

                self.scanner._set_resource_context(ns, 'v1', 'Namespace')

                quotas = self.scanner.v1.list_namespaced_resource_quota(ns_name)
                if not quotas.items:
                    await self.scanner.report_finding({
                        "resource_type": "Namespace",
                        "resource_name": ns_name,
                        "namespace": ns_name,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": "Namespace has no ResourceQuota",
                        "description": f"Namespace '{ns_name}' has no ResourceQuota configured. Workloads can consume unlimited cluster resources.",
                        "remediation": "Create a ResourceQuota to limit the total resources (CPU, memory, storage, object count) that can be consumed in this namespace.",
                        "timestamp": timestamp
                    })

                limit_ranges = self.scanner.v1.list_namespaced_limit_range(ns_name)
                if not limit_ranges.items:
                    await self.scanner.report_finding({
                        "resource_type": "Namespace",
                        "resource_name": ns_name,
                        "namespace": ns_name,
                        "severity": "low",
                        "category": "Best Practice",
                        "title": "Namespace has no LimitRange",
                        "description": f"Namespace '{ns_name}' has no LimitRange configured. Containers without resource limits can consume unlimited resources.",
                        "remediation": "Create a LimitRange to set default resource limits and requests for containers in this namespace.",
                        "timestamp": timestamp
                    })

            logger.info("ResourceQuota and LimitRange scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning ResourceQuotas: {e}")
        except Exception as e:
            logger.error(f"Error scanning ResourceQuotas: {e}")

    async def scan_configmaps(self):
        """Scan ConfigMaps for sensitive data patterns"""
        logger.info("Scanning ConfigMaps for sensitive data...")
        try:
            configmaps = self.scanner.v1.list_config_map_for_all_namespaces()
            timestamp = datetime.utcnow().isoformat() + "Z"

            sensitive_patterns = [
                (r'password\s*[=:]\s*\S+', 'password'),
                (r'api[_-]?key\s*[=:]\s*\S+', 'API key'),
                (r'secret[_-]?key\s*[=:]\s*\S+', 'secret key'),
                (r'access[_-]?token\s*[=:]\s*\S+', 'access token'),
                (r'private[_-]?key', 'private key'),
                (r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----', 'private key'),
                (r'aws[_-]?secret[_-]?access[_-]?key', 'AWS secret'),
            ]

            sensitive_keys = [
                'password', 'passwd', 'secret', 'token', 'api_key', 'apikey',
                'private_key', 'privatekey', 'credentials', 'auth'
            ]

            for cm in configmaps.items:
                if self.scanner.exclusion_mgr.is_namespace_excluded(cm.metadata.namespace):
                    continue

                cm_name = cm.metadata.name
                namespace = cm.metadata.namespace
                data = cm.data or {}
                self.scanner._clear_resource_context()

                found_sensitive = set()

                for key, value in data.items():
                    key_lower = key.lower()
                    for sensitive_key in sensitive_keys:
                        if sensitive_key in key_lower:
                            found_sensitive.add(f"key '{key}' (contains '{sensitive_key}')")
                            break

                    if value:
                        for pattern, pattern_name in sensitive_patterns:
                            if re.search(pattern, value, re.IGNORECASE):
                                found_sensitive.add(f"value matching '{pattern_name}' pattern")
                                break

                if found_sensitive:
                    await self.scanner.report_finding({
                        "resource_type": "ConfigMap",
                        "resource_name": cm_name,
                        "namespace": namespace,
                        "severity": "high",
                        "category": "Security",
                        "title": "ConfigMap may contain sensitive data",
                        "description": f"ConfigMap '{cm_name}' appears to contain sensitive data: {', '.join(list(found_sensitive)[:3])}. ConfigMaps are not encrypted and should not store secrets.",
                        "remediation": "Move sensitive data to Kubernetes Secrets (which can be encrypted at rest) or use external secret management like HashiCorp Vault.",
                        "timestamp": timestamp
                    })

            logger.info("ConfigMap scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning ConfigMaps: {e}")
        except Exception as e:
            logger.error(f"Error scanning ConfigMaps: {e}")

    async def scan_cronjobs(self):
        """Scan all CronJobs for security issues"""
        logger.info("Scanning CronJobs and Jobs...")
        try:
            cronjobs = self.scanner.batch_v1.list_cron_job_for_all_namespaces()
            for cronjob in cronjobs.items:
                if self.scanner.exclusion_mgr.is_namespace_excluded(cronjob.metadata.namespace):
                    continue
                await self.scan_single_cronjob(cronjob)
            logger.info("CronJob scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning CronJobs: {e}")
        except Exception as e:
            logger.error(f"Error scanning CronJobs: {e}")

    async def scan_persistent_volumes(self):
        """Scan PersistentVolumes for security issues"""
        logger.info("Scanning PersistentVolumes...")
        try:
            pvs = self.scanner.v1.list_persistent_volume()
            timestamp = datetime.utcnow().isoformat() + "Z"

            for pv in pvs.items:
                pv_name = pv.metadata.name
                self.scanner._set_resource_context(pv, 'v1', 'PersistentVolume')

                if pv.spec.host_path:
                    host_path = pv.spec.host_path.path
                    severity = "critical" if host_path in ['/', '/etc', '/var', '/root', '/home'] else "high"
                    await self.scanner.report_finding({
                        "resource_type": "PersistentVolume",
                        "resource_name": pv_name,
                        "namespace": "cluster-wide",
                        "severity": severity,
                        "category": "Security",
                        "title": f"PersistentVolume uses hostPath: {host_path}",
                        "description": f"PersistentVolume '{pv_name}' uses hostPath '{host_path}'. This provides direct access to the host filesystem and can lead to container escape or data exposure.",
                        "remediation": "Use cloud provider storage classes, NFS, or other network-attached storage instead of hostPath for PersistentVolumes.",
                        "timestamp": timestamp
                    })

                if pv.spec.local:
                    local_path = pv.spec.local.path
                    await self.scanner.report_finding({
                        "resource_type": "PersistentVolume",
                        "resource_name": pv_name,
                        "namespace": "cluster-wide",
                        "severity": "medium",
                        "category": "Security",
                        "title": f"PersistentVolume uses local storage: {local_path}",
                        "description": f"PersistentVolume '{pv_name}' uses local storage at '{local_path}'. Local volumes are node-specific and may expose host filesystem.",
                        "remediation": "Consider using network-attached storage for better isolation and portability.",
                        "timestamp": timestamp
                    })

            logger.info("PersistentVolume scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning PersistentVolumes: {e}")
        except Exception as e:
            logger.error(f"Error scanning PersistentVolumes: {e}")
