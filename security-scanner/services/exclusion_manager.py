import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from services.security_scanner import SecurityScanner

from services.scanner_base import SYSTEM_NAMESPACES

logger = logging.getLogger(__name__)


class ExclusionManager:
    """Manages exclusion caches (namespaces, rules, registries) and handles real-time changes."""

    def __init__(self, scanner: 'SecurityScanner'):
        self.scanner = scanner
        # Cache for admin-configured excluded namespaces
        self.excluded_namespaces: List[str] = []
        self.excluded_namespaces_last_refresh: Optional[datetime] = None
        self.excluded_namespaces_refresh_interval = timedelta(minutes=1)
        # Cache for admin-configured excluded rules
        self.globally_excluded_rules: Set[str] = set()
        self.namespace_excluded_rules: Dict[str, Set[str]] = {}
        self.excluded_rules_last_refresh: Optional[datetime] = None
        self.excluded_rules_refresh_interval = timedelta(minutes=1)
        # Cache for admin-configured trusted registries
        self.admin_trusted_registries: List[str] = []
        self._trusted_registries_last_refresh: Optional[datetime] = None
        self._trusted_registries_refresh_interval = timedelta(minutes=1)

    async def refresh_excluded_namespaces(self, force: bool = False) -> bool:
        """Refresh the excluded namespaces cache from backend"""
        now = datetime.utcnow()
        if (force or self.excluded_namespaces_last_refresh is None or
                now - self.excluded_namespaces_last_refresh > self.excluded_namespaces_refresh_interval):
            try:
                namespaces = await self.scanner.backend_client.get_excluded_namespaces()
                self.excluded_namespaces = namespaces
                self.excluded_namespaces_last_refresh = now
                if self.excluded_namespaces:
                    logger.info(f"Refreshed excluded namespaces: {self.excluded_namespaces}")
                else:
                    logger.info("No excluded namespaces configured")
                return True
            except Exception as e:
                logger.warning(f"Failed to refresh excluded namespaces: {e}")
                return False
        return True

    def is_namespace_excluded(self, namespace: str) -> bool:
        """Check if a namespace is excluded from scanning"""
        if namespace in SYSTEM_NAMESPACES:
            return True
        if namespace in self.excluded_namespaces:
            return True
        return False

    async def refresh_excluded_rules(self, force: bool = False) -> bool:
        """Refresh the excluded rules cache from backend"""
        now = datetime.utcnow()
        if (force or self.excluded_rules_last_refresh is None or
                now - self.excluded_rules_last_refresh > self.excluded_rules_refresh_interval):
            try:
                rules = await self.scanner.backend_client.get_excluded_rules()
                globally_excluded = set()
                namespace_excluded = {}
                for rule in rules:
                    rule_title = rule.get('rule_title')
                    namespace = rule.get('namespace')
                    if not rule_title:
                        continue
                    if namespace is None:
                        globally_excluded.add(rule_title)
                    else:
                        if namespace not in namespace_excluded:
                            namespace_excluded[namespace] = set()
                        namespace_excluded[namespace].add(rule_title)
                self.globally_excluded_rules = globally_excluded
                self.namespace_excluded_rules = namespace_excluded
                self.excluded_rules_last_refresh = now
                if globally_excluded or namespace_excluded:
                    logger.info(f"Refreshed excluded rules: global={globally_excluded}, namespaced={namespace_excluded}")
                else:
                    logger.info("No excluded rules configured")
                return True
            except Exception as e:
                logger.warning(f"Failed to refresh excluded rules: {e}")
                return False
        return True

    async def refresh_trusted_registries(self, force: bool = False) -> bool:
        """Refresh the admin-added trusted registries cache from backend"""
        now = datetime.utcnow()
        if (force or self._trusted_registries_last_refresh is None or
                now - self._trusted_registries_last_refresh > self._trusted_registries_refresh_interval):
            try:
                registries = await self.scanner.backend_client.get_trusted_registries()
                self.admin_trusted_registries = registries
                self._trusted_registries_last_refresh = now
                if self.admin_trusted_registries:
                    logger.info(f"Refreshed admin trusted registries: {self.admin_trusted_registries}")
                return True
            except Exception as e:
                logger.warning(f"Failed to refresh trusted registries: {e}")
                return False
        return True

    def is_rule_excluded(self, title: str, namespace: str = '') -> bool:
        """Check if a rule title is excluded (globally or for given namespace).
        Supports base-name matching: excluding 'Privilege escalation allowed' also
        matches 'Privilege escalation allowed: container-name'."""
        if title in self.globally_excluded_rules:
            return True
        if ': ' in title:
            base_name = title.split(': ', 1)[0]
            if base_name in self.globally_excluded_rules:
                return True
        if namespace and namespace in self.namespace_excluded_rules:
            ns_rules = self.namespace_excluded_rules[namespace]
            if title in ns_rules:
                return True
            if ': ' in title:
                base_name = title.split(': ', 1)[0]
                if base_name in ns_rules:
                    return True
        return False

    async def handle_namespace_change(self, namespace: str, action: str):
        """Handle real-time namespace exclusion changes from WebSocket"""
        try:
            await self.refresh_excluded_namespaces(force=True)
            if action == "included":
                if not self.is_namespace_excluded(namespace):
                    logger.info(f"Namespace '{namespace}' included - rescanning...")
                    await self._scan_namespace_pods(namespace)
            elif action == "excluded":
                logger.info(f"Namespace '{namespace}' excluded - exclusion list updated")
        except Exception as e:
            logger.error(f"Error handling namespace change: {e}")

    async def handle_rule_change(self, rule_title: str, action: str, namespace: str = None):
        """Handle real-time rule exclusion changes from WebSocket"""
        try:
            await self.refresh_excluded_rules(force=True)
            if action == "included":
                if namespace:
                    if not self.is_rule_excluded(rule_title, namespace):
                        logger.info(f"Rule '{rule_title}' included for namespace '{namespace}' - rescanning namespace...")
                        await self._scan_namespace_pods(namespace)
                else:
                    if not self.is_rule_excluded(rule_title):
                        logger.info(f"Rule '{rule_title}' included globally - rescanning cluster...")
                        await self.scanner.scan_cluster()
            elif action == "excluded":
                scope = f"for namespace '{namespace}'" if namespace else "globally"
                logger.info(f"Rule '{rule_title}' excluded {scope} - exclusion list updated")
        except Exception as e:
            logger.error(f"Error handling rule change: {e}")

    async def handle_registry_change(self, registry: str, action: str):
        """Handle real-time trusted registry changes from WebSocket"""
        logger.info(f"Handling registry change: {registry} -> {action}")
        try:
            await self.refresh_trusted_registries(force=True)
            logger.info("Refreshed trusted registries")

            logger.info("Sending rescan status: started")
            result = await self.scanner.backend_client.report_rescan_status("started", "trusted_registry_change")
            logger.info(f"Rescan status 'started' sent, result: {result}")

            logger.info(f"Trusted registry '{registry}' {action} - rescanning all pods...")
            await self._rescan_all_pods()

            logger.info("Sending rescan status: completed")
            await self.scanner.backend_client.report_rescan_status("completed", "trusted_registry_change")
            logger.info("Rescan status 'completed' sent")
        except Exception as e:
            logger.error(f"Error handling registry change: {e}")
            await self.scanner.backend_client.report_rescan_status("completed", "trusted_registry_change")

    async def _rescan_all_pods(self):
        """Re-scan all pods across all non-excluded namespaces"""
        try:
            pods = self.scanner.v1.list_pod_for_all_namespaces()
            for pod in pods.items:
                namespace = pod.metadata.namespace
                if not self.is_namespace_excluded(namespace):
                    await self.scanner.pod_scanner.scan_single_pod(pod)
        except Exception as e:
            logger.error(f"Error rescanning all pods: {e}")

    async def _scan_namespace_pods(self, namespace: str):
        """Scan all pods in a specific namespace"""
        try:
            pods = self.scanner.v1.list_namespaced_pod(namespace)
            for pod in pods.items:
                await self.scanner.pod_scanner.scan_single_pod(pod)
        except Exception as e:
            logger.error(f"Error scanning namespace {namespace}: {e}")
