import asyncio
import logging
import os
from datetime import datetime
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from services.backend_client import BackendClient

logger = logging.getLogger(__name__)


class SecurityScanner:
    def __init__(self):
        self.backend_url = os.getenv("BACKEND_URL", "http://kure-backend:8000")
        self.scan_interval = int(os.getenv("SCAN_INTERVAL", "3600"))  # Default: 1 hour
        self.backend_client = BackendClient(self.backend_url)
        self.v1 = None
        self.apps_v1 = None
        self.rbac_v1 = None

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

    async def scan_pods(self):
        """Scan pods for security issues"""
        logger.info("Scanning pods for security issues...")
        try:
            pods = self.v1.list_pod_for_all_namespaces()

            for pod in pods.items:
                # Skip pods in kube-system namespace
                if pod.metadata.namespace in ['kube-system', 'kube-public', 'kube-node-lease']:
                    continue

                timestamp = datetime.utcnow().isoformat() + "Z"

                # Check for privileged containers
                if pod.spec.containers:
                    for container in pod.spec.containers:
                        if container.security_context and container.security_context.privileged:
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod.metadata.name,
                                "namespace": pod.metadata.namespace,
                                "severity": "high",
                                "category": "Security",
                                "title": "Privileged container detected",
                                "description": f"Container '{container.name}' is running in privileged mode, which grants access to all host devices and capabilities.",
                                "remediation": "Remove 'privileged: true' from the container's securityContext unless absolutely necessary. Use specific capabilities instead.",
                                "timestamp": timestamp
                            })

                        # Check for missing resource limits
                        if not container.resources or not container.resources.limits:
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod.metadata.name,
                                "namespace": pod.metadata.namespace,
                                "severity": "medium",
                                "category": "Best Practice",
                                "title": "Container missing resource limits",
                                "description": f"Container '{container.name}' does not have resource limits defined, which can lead to resource exhaustion.",
                                "remediation": "Add resource limits (CPU and memory) to the container specification.",
                                "timestamp": timestamp
                            })

                        # Check for running as root
                        if not container.security_context or container.security_context.run_as_non_root is None or not container.security_context.run_as_non_root:
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod.metadata.name,
                                "namespace": pod.metadata.namespace,
                                "severity": "medium",
                                "category": "Security",
                                "title": "Container may run as root",
                                "description": f"Container '{container.name}' does not explicitly prevent running as root user.",
                                "remediation": "Set 'runAsNonRoot: true' in the container's securityContext.",
                                "timestamp": timestamp
                            })

                        # Check for hostNetwork
                        if pod.spec.host_network:
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod.metadata.name,
                                "namespace": pod.metadata.namespace,
                                "severity": "high",
                                "category": "Security",
                                "title": "Pod uses host network",
                                "description": "Pod is using the host network namespace, which can expose host network to the container.",
                                "remediation": "Remove 'hostNetwork: true' unless required for specific use cases like CNI plugins.",
                                "timestamp": timestamp
                            })

                        # Check for hostPID
                        if pod.spec.host_pid:
                            await self.report_finding({
                                "resource_type": "Pod",
                                "resource_name": pod.metadata.name,
                                "namespace": pod.metadata.namespace,
                                "severity": "high",
                                "category": "Security",
                                "title": "Pod uses host PID namespace",
                                "description": "Pod is using the host PID namespace, which allows viewing all processes on the host.",
                                "remediation": "Remove 'hostPID: true' unless absolutely necessary.",
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

                # Check for LoadBalancer services
                if service.spec.type == "LoadBalancer":
                    await self.report_finding({
                        "resource_type": "Service",
                        "resource_name": service.metadata.name,
                        "namespace": service.metadata.namespace,
                        "severity": "medium",
                        "category": "Security",
                        "title": "Service exposed via LoadBalancer",
                        "description": "Service is exposed externally via LoadBalancer, which may be accessible from the internet.",
                        "remediation": "Review if external exposure is necessary. Consider using ClusterIP with Ingress controller for better control.",
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

                # Check for wildcard permissions
                if role.rules:
                    for rule in role.rules:
                        if rule.resources and '*' in rule.resources:
                            await self.report_finding({
                                "resource_type": "ClusterRole",
                                "resource_name": role.metadata.name,
                                "namespace": "cluster-wide",
                                "severity": "high",
                                "category": "Security",
                                "title": "ClusterRole with wildcard resource permissions",
                                "description": f"ClusterRole '{role.metadata.name}' has wildcard (*) resource permissions, which grants access to all resources.",
                                "remediation": "Restrict permissions to specific resources instead of using wildcards.",
                                "timestamp": timestamp
                            })
                            break

                        if rule.verbs and '*' in rule.verbs:
                            await self.report_finding({
                                "resource_type": "ClusterRole",
                                "resource_name": role.metadata.name,
                                "namespace": "cluster-wide",
                                "severity": "high",
                                "category": "Security",
                                "title": "ClusterRole with wildcard verb permissions",
                                "description": f"ClusterRole '{role.metadata.name}' has wildcard (*) verb permissions, which grants all actions.",
                                "remediation": "Restrict permissions to specific verbs (get, list, watch, create, update, delete) instead of using wildcards.",
                                "timestamp": timestamp
                            })
                            break

            logger.info("RBAC security scan completed")
        except ApiException as e:
            logger.error(f"Kubernetes API error while scanning RBAC: {e}")
        except Exception as e:
            logger.error(f"Error scanning RBAC: {e}")

    async def report_finding(self, finding_data: dict):
        """Report a security finding to the backend"""
        await self.backend_client.report_security_finding(finding_data)