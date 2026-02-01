import logging
from .database_base import DatabaseInterface

logger = logging.getLogger(__name__)


def get_database() -> DatabaseInterface:
    """
    Factory function to get PostgreSQL database implementation.
    
    Returns:
        - PostgreSQLDatabase (only supported database)
    """
    
    logger.info("Using PostgreSQL database")
    try:
        from .database_postgresql import PostgreSQLDatabase
        return PostgreSQLDatabase()
    except ImportError as e:
        logger.error(f"PostgreSQL dependencies not available: {e}")
        raise ImportError("PostgreSQL is required but dependencies are not available")


# For backward compatibility, create a Database class that wraps the factory function
class Database:
    def __init__(self):
        self._db = get_database()

    async def init_database(self):
        return await self._db.init_database()

    async def save_pod_failure(self, failure):
        return await self._db.save_pod_failure(failure)

    async def get_pod_failures(self, status_filter=None, include_dismissed=False, dismissed_only=False):
        return await self._db.get_pod_failures(status_filter, include_dismissed, dismissed_only)

    async def get_pod_failure_by_id(self, failure_id):
        return await self._db.get_pod_failure_by_id(failure_id)

    async def update_pod_solution(self, failure_id, solution):
        return await self._db.update_pod_solution(failure_id, solution)

    async def update_pod_status(self, failure_id, status, resolution_note=None):
        return await self._db.update_pod_status(failure_id, status, resolution_note)

    async def dismiss_pod_failure(self, failure_id):
        return await self._db.dismiss_pod_failure(failure_id)

    async def restore_pod_failure(self, failure_id):
        return await self._db.restore_pod_failure(failure_id)

    async def dismiss_deleted_pod(self, namespace, pod_name):
        """Returns list of auto-resolved PodFailureResponse objects"""
        return await self._db.dismiss_deleted_pod(namespace, pod_name)

    async def save_security_finding(self, finding):
        return await self._db.save_security_finding(finding)

    async def get_security_findings(self, include_dismissed=False, dismissed_only=False):
        return await self._db.get_security_findings(include_dismissed, dismissed_only)

    async def dismiss_security_finding(self, finding_id):
        return await self._db.dismiss_security_finding(finding_id)

    async def restore_security_finding(self, finding_id):
        return await self._db.restore_security_finding(finding_id)

    async def clear_security_findings(self):
        return await self._db.clear_security_findings()

    async def delete_findings_by_resource(self, resource_type, namespace, resource_name):
        return await self._db.delete_findings_by_resource(resource_type, namespace, resource_name)

    async def close(self):
        return await self._db.close()

    # Excluded namespaces methods
    async def add_excluded_namespace(self, namespace):
        return await self._db.add_excluded_namespace(namespace)

    async def remove_excluded_namespace(self, namespace):
        return await self._db.remove_excluded_namespace(namespace)

    async def get_excluded_namespaces(self):
        return await self._db.get_excluded_namespaces()

    async def is_namespace_excluded(self, namespace):
        return await self._db.is_namespace_excluded(namespace)

    async def get_all_namespaces(self):
        return await self._db.get_all_namespaces()

    async def delete_findings_by_namespace(self, namespace):
        return await self._db.delete_findings_by_namespace(namespace)

    async def delete_pod_failures_by_namespace(self, namespace):
        return await self._db.delete_pod_failures_by_namespace(namespace)

    # Excluded pods methods (pod monitoring exclusions - by pod name only)
    async def add_excluded_pod(self, pod_name):
        return await self._db.add_excluded_pod(pod_name)

    async def remove_excluded_pod(self, pod_name):
        return await self._db.remove_excluded_pod(pod_name)

    async def get_excluded_pods(self):
        return await self._db.get_excluded_pods()

    async def is_pod_excluded(self, pod_name):
        return await self._db.is_pod_excluded(pod_name)

    async def get_all_monitored_pods(self):
        return await self._db.get_all_monitored_pods()

    async def delete_pod_failure_by_pod(self, pod_name):
        return await self._db.delete_pod_failure_by_pod(pod_name)

    # Excluded rules methods (security rule exclusions)
    async def add_excluded_rule(self, rule_title, namespace=''):
        return await self._db.add_excluded_rule(rule_title, namespace)

    async def remove_excluded_rule(self, rule_title, namespace=''):
        return await self._db.remove_excluded_rule(rule_title, namespace)

    async def get_excluded_rules(self):
        return await self._db.get_excluded_rules()

    async def is_rule_excluded(self, rule_title, namespace=''):
        return await self._db.is_rule_excluded(rule_title, namespace)

    async def get_all_rule_titles(self, namespace=None):
        return await self._db.get_all_rule_titles(namespace)

    async def delete_findings_by_rule_title(self, rule_title, namespace=None):
        return await self._db.delete_findings_by_rule_title(rule_title, namespace)

    # Notification settings methods
    async def save_notification_setting(self, setting):
        return await self._db.save_notification_setting(setting)

    async def get_notification_settings(self):
        return await self._db.get_notification_settings()

    async def get_notification_setting(self, provider):
        return await self._db.get_notification_setting(provider)

    async def get_enabled_notification_settings(self):
        return await self._db.get_enabled_notification_settings()

    async def update_notification_setting(self, provider, setting):
        return await self._db.update_notification_setting(provider, setting)

    async def delete_notification_setting(self, provider):
        return await self._db.delete_notification_setting(provider)

    # LLM Configuration methods
    async def save_llm_config(self, provider, api_key, model=None):
        return await self._db.save_llm_config(provider, api_key, model)

    async def get_llm_config(self):
        return await self._db.get_llm_config()

    async def delete_llm_config(self):
        return await self._db.delete_llm_config()

    # App settings methods
    async def get_app_setting(self, key):
        return await self._db.get_app_setting(key)

    async def set_app_setting(self, key, value):
        return await self._db.set_app_setting(key, value)

    # Pod record deletion methods
    async def delete_pod_failure(self, failure_id):
        return await self._db.delete_pod_failure(failure_id)

    async def cleanup_old_resolved_pods(self, retention_minutes):
        return await self._db.cleanup_old_resolved_pods(retention_minutes)

