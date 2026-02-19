import logging
import os
import yaml
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# Kyverno CRD coordinates
KYVERNO_GROUP = "kyverno.io"
KYVERNO_VERSION = "v1"
KYVERNO_PLURAL = "clusterpolicies"

# PolicyReport CRD coordinates
POLICY_REPORT_GROUP = "wgpolicyk8s.io"
POLICY_REPORT_VERSION = "v1alpha2"
POLICY_REPORT_PLURAL = "policyreports"
CLUSTER_POLICY_REPORT_PLURAL = "clusterpolicyreports"

KURE_LABEL = "app.kubernetes.io/managed-by"
KURE_LABEL_VALUE = "kure-monitor"
KURE_PREFIX = "kure-"

# Official Kyverno install manifest
KYVERNO_INSTALL_URL = "https://github.com/kyverno/kyverno/releases/latest/download/install.yaml"

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "policies" / "templates"


class PolicyEngine:
    def __init__(self, db):
        self._db = db
        self._k8s_available = False
        self._custom_api = None
        self._apps_api = None
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            keep_trailing_newline=True,
        )

    async def initialize(self):
        """Initialize K8s client, seed policies to DB, and reconcile with cluster."""
        # Seed policy definitions into database
        from policies.registry import KYVERNO_POLICIES
        await self._db.seed_kyverno_policies(KYVERNO_POLICIES)
        logger.info(f"Seeded {len(KYVERNO_POLICIES)} Kyverno policy definitions to database")

        # Initialize Kubernetes client
        try:
            from kubernetes import client, config as k8s_config
            try:
                k8s_config.load_incluster_config()
            except k8s_config.ConfigException:
                try:
                    k8s_config.load_kube_config()
                except k8s_config.ConfigException:
                    logger.warning("Could not configure Kubernetes client for Kyverno policy management")
                    return

            self._custom_api = client.CustomObjectsApi()
            self._apps_api = client.AppsV1Api()
            self._k8s_available = True
            logger.info("Kubernetes client initialized for Kyverno policy management")

            # Reconcile on startup
            await self.reconcile()

        except ImportError:
            logger.warning("kubernetes package not available - Kyverno policy management disabled")
        except Exception as e:
            logger.error(f"Error initializing PolicyEngine: {e}")

    async def check_kyverno_status(self) -> dict:
        """Check if Kyverno deployment exists and is ready."""
        result = {
            "kyverno_installed": False,
            "kyverno_version": None,
            "kyverno_ready": False,
            "managed_policies": 0,
            "active_policies": 0,
            "total_violations": 0,
        }

        if not self._k8s_available:
            return result

        try:
            # Check for Kyverno deployment in common namespaces
            for ns in ["kyverno", "kyverno-system"]:
                try:
                    deployments = self._apps_api.list_namespaced_deployment(
                        namespace=ns,
                        label_selector="app.kubernetes.io/name=kyverno"
                    )
                    if deployments.items:
                        dep = deployments.items[0]
                        result["kyverno_installed"] = True
                        result["kyverno_version"] = dep.metadata.labels.get(
                            "app.kubernetes.io/version", "unknown"
                        )
                        result["kyverno_ready"] = (
                            dep.status.ready_replicas is not None
                            and dep.status.ready_replicas > 0
                        )
                        break
                except Exception:
                    continue

            # Get policy counts from database
            all_policies = await self._db.get_kyverno_policies()
            result["managed_policies"] = len(all_policies)
            result["active_policies"] = sum(1 for p in all_policies if p.enabled)

            # Get violation count
            if result["kyverno_installed"]:
                violations = await self.get_violations()
                result["total_violations"] = len(violations)

        except Exception as e:
            logger.error(f"Error checking Kyverno status: {e}")

        return result

    async def install_kyverno(self) -> dict:
        """Install Kyverno via kubectl apply of official install manifest."""
        if not self._k8s_available:
            return {"success": False, "message": "Kubernetes client not available"}

        try:
            import subprocess
            proc = subprocess.run(
                ["kubectl", "apply", "-f", KYVERNO_INSTALL_URL],
                capture_output=True, text=True, timeout=120
            )

            if proc.returncode == 0:
                logger.info("Kyverno installation initiated successfully")
                return {
                    "success": True,
                    "message": "Kyverno installation initiated. It may take a few minutes to become ready.",
                    "output": proc.stdout
                }
            else:
                logger.error(f"Kyverno installation failed: {proc.stderr}")
                return {
                    "success": False,
                    "message": f"Installation failed: {proc.stderr}"
                }
        except FileNotFoundError:
            return {"success": False, "message": "kubectl not found"}
        except subprocess.TimeoutExpired:
            return {"success": False, "message": "Installation timed out (120s)"}
        except Exception as e:
            logger.error(f"Error installing Kyverno: {e}")
            return {"success": False, "message": str(e)}

    async def apply_policy(self, policy_id: str) -> bool:
        """Render Jinja2 template and create/update ClusterPolicy CRD."""
        if not self._k8s_available:
            logger.warning("Cannot apply policy - Kubernetes client not available")
            return False

        try:
            # Get policy config from database
            policy = await self._db.get_kyverno_policy(policy_id)
            if not policy:
                logger.error(f"Policy {policy_id} not found in database")
                return False

            # Render template
            rendered = self._render_template(policy)
            if not rendered:
                return False

            # Parse rendered YAML
            body = yaml.safe_load(rendered)
            policy_name = f"{KURE_PREFIX}{policy_id}"

            # Create or update the ClusterPolicy
            try:
                # Try to get existing policy
                self._custom_api.get_cluster_custom_object(
                    group=KYVERNO_GROUP,
                    version=KYVERNO_VERSION,
                    plural=KYVERNO_PLURAL,
                    name=policy_name,
                )
                # Exists - update it
                self._custom_api.replace_cluster_custom_object(
                    group=KYVERNO_GROUP,
                    version=KYVERNO_VERSION,
                    plural=KYVERNO_PLURAL,
                    name=policy_name,
                    body=body,
                )
                logger.info(f"Updated ClusterPolicy: {policy_name}")
            except Exception:
                # Does not exist - create it
                self._custom_api.create_cluster_custom_object(
                    group=KYVERNO_GROUP,
                    version=KYVERNO_VERSION,
                    plural=KYVERNO_PLURAL,
                    body=body,
                )
                logger.info(f"Created ClusterPolicy: {policy_name}")

            # Mark as synced
            await self._db.set_kyverno_policy_synced(policy_id, True)
            return True

        except Exception as e:
            logger.error(f"Error applying policy {policy_id}: {e}")
            await self._db.set_kyverno_policy_synced(policy_id, False)
            return False

    async def remove_policy(self, policy_id: str) -> bool:
        """Delete ClusterPolicy CRD from cluster."""
        if not self._k8s_available:
            logger.warning("Cannot remove policy - Kubernetes client not available")
            return False

        policy_name = f"{KURE_PREFIX}{policy_id}"
        try:
            self._custom_api.delete_cluster_custom_object(
                group=KYVERNO_GROUP,
                version=KYVERNO_VERSION,
                plural=KYVERNO_PLURAL,
                name=policy_name,
            )
            logger.info(f"Deleted ClusterPolicy: {policy_name}")
            await self._db.set_kyverno_policy_synced(policy_id, True)
            return True
        except Exception as e:
            # 404 is fine - policy already gone
            if hasattr(e, 'status') and e.status == 404:
                logger.info(f"ClusterPolicy {policy_name} already absent")
                await self._db.set_kyverno_policy_synced(policy_id, True)
                return True
            logger.error(f"Error removing policy {policy_id}: {e}")
            return False

    async def reconcile(self):
        """On startup: apply enabled policies missing from cluster, remove disabled ones."""
        if not self._k8s_available:
            logger.info("Skipping Kyverno reconciliation - Kubernetes client not available")
            return

        logger.info("Starting Kyverno policy reconciliation...")

        try:
            # Get current cluster state - list all kure-managed ClusterPolicies
            cluster_policies = set()
            try:
                result = self._custom_api.list_cluster_custom_object(
                    group=KYVERNO_GROUP,
                    version=KYVERNO_VERSION,
                    plural=KYVERNO_PLURAL,
                    label_selector=f"{KURE_LABEL}={KURE_LABEL_VALUE}",
                )
                for item in result.get("items", []):
                    name = item["metadata"]["name"]
                    if name.startswith(KURE_PREFIX):
                        cluster_policies.add(name[len(KURE_PREFIX):])
            except Exception as e:
                # Kyverno CRD may not exist yet
                logger.warning(f"Could not list Kyverno ClusterPolicies (Kyverno may not be installed): {e}")
                return

            # Get desired state from database
            all_policies = await self._db.get_kyverno_policies()
            enabled_ids = {p.policy_id for p in all_policies if p.enabled}
            disabled_ids = {p.policy_id for p in all_policies if not p.enabled}

            # Apply missing enabled policies
            to_apply = enabled_ids - cluster_policies
            for pid in to_apply:
                logger.info(f"Reconcile: applying missing policy {pid}")
                await self.apply_policy(pid)

            # Update existing enabled policies (re-apply to sync config)
            to_update = enabled_ids & cluster_policies
            for pid in to_update:
                policy = next((p for p in all_policies if p.policy_id == pid), None)
                if policy and not policy.synced:
                    logger.info(f"Reconcile: updating unsynced policy {pid}")
                    await self.apply_policy(pid)

            # Remove orphaned policies (disabled but still in cluster)
            to_remove = disabled_ids & cluster_policies
            for pid in to_remove:
                logger.info(f"Reconcile: removing disabled policy {pid}")
                await self.remove_policy(pid)

            logger.info(
                f"Reconciliation complete: applied={len(to_apply)}, "
                f"updated={sum(1 for p in all_policies if p.policy_id in to_update and not p.synced)}, "
                f"removed={len(to_remove)}"
            )

        except Exception as e:
            logger.error(f"Error during Kyverno reconciliation: {e}")

    async def get_violations(self) -> list:
        """Read PolicyReport/ClusterPolicyReport CRDs for kure-managed violations."""
        violations = []
        if not self._k8s_available:
            return violations

        try:
            # Get enabled policy names for filtering
            enabled_policies = await self._db.get_enabled_kyverno_policies()
            kure_policy_names = {f"{KURE_PREFIX}{p.policy_id}" for p in enabled_policies}

            if not kure_policy_names:
                return violations

            # Read namespace-scoped PolicyReports
            try:
                reports = self._custom_api.list_cluster_custom_object(
                    group=POLICY_REPORT_GROUP,
                    version=POLICY_REPORT_VERSION,
                    plural=POLICY_REPORT_PLURAL,
                )
                violations.extend(
                    self._extract_violations(reports, kure_policy_names)
                )
            except Exception as e:
                logger.debug(f"Could not read PolicyReports: {e}")

            # Read ClusterPolicyReports
            try:
                cluster_reports = self._custom_api.list_cluster_custom_object(
                    group=POLICY_REPORT_GROUP,
                    version=POLICY_REPORT_VERSION,
                    plural=CLUSTER_POLICY_REPORT_PLURAL,
                )
                violations.extend(
                    self._extract_violations(cluster_reports, kure_policy_names)
                )
            except Exception as e:
                logger.debug(f"Could not read ClusterPolicyReports: {e}")

        except Exception as e:
            logger.error(f"Error fetching Kyverno violations: {e}")

        return violations

    def _extract_violations(self, reports: dict, kure_policy_names: set) -> list:
        """Extract violation entries from PolicyReport items."""
        violations = []
        for item in reports.get("items", []):
            for result in item.get("results", []):
                policy_name = result.get("policy", "")
                if policy_name not in kure_policy_names:
                    continue
                if result.get("result") != "fail":
                    continue

                # Extract resource info
                resources = result.get("resources", [{}])
                resource = resources[0] if resources else {}

                # Map policy name back to registry info
                policy_id = policy_name[len(KURE_PREFIX):] if policy_name.startswith(KURE_PREFIX) else policy_name
                category = result.get("category", "")
                severity = result.get("severity", "medium")

                violations.append({
                    "policy_name": policy_name,
                    "rule_name": result.get("rule", ""),
                    "resource_kind": resource.get("kind", ""),
                    "resource_name": resource.get("name", ""),
                    "resource_namespace": resource.get("namespace", item.get("metadata", {}).get("namespace", "")),
                    "message": result.get("message", ""),
                    "severity": severity,
                    "category": category,
                    "timestamp": result.get("timestamp", ""),
                })

        return violations

    def _render_template(self, policy) -> str:
        """Render Jinja2 YAML template with policy config."""
        template_file = f"{policy.policy_id}.yaml"
        try:
            template = self._jinja_env.get_template(template_file)

            # Map mode to Kyverno validationFailureAction
            mode = "Enforce" if policy.mode == "enforce" else "Audit"

            rendered = template.render(
                mode=mode,
                excluded_namespaces=policy.excluded_namespaces or [],
                excluded_deployments=policy.excluded_deployments or [],
            )
            return rendered
        except Exception as e:
            logger.error(f"Error rendering template {template_file}: {e}")
            return ""
