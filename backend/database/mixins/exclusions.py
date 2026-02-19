import logging
from typing import List
from models.models import ExcludedNamespaceResponse, TrustedRegistryResponse

logger = logging.getLogger(__name__)


class ExclusionMixin:
    """Namespace/pod/rule exclusions + trusted registries. Requires self._acquire()."""

    # --- Excluded namespaces ---

    async def add_excluded_namespace(self, namespace: str) -> ExcludedNamespaceResponse:
        """Add a namespace to the exclusion list"""
        async with self._acquire() as conn:
            try:
                result = await conn.fetchrow(
                    """INSERT INTO excluded_namespaces (namespace)
                       VALUES ($1)
                       ON CONFLICT (namespace) DO NOTHING
                       RETURNING id, namespace, created_at""",
                    namespace
                )
                if result:
                    return ExcludedNamespaceResponse(
                        id=result['id'],
                        namespace=result['namespace'],
                        created_at=result['created_at'].isoformat()
                    )
                existing = await conn.fetchrow(
                    "SELECT id, namespace, created_at FROM excluded_namespaces WHERE namespace = $1",
                    namespace
                )
                return ExcludedNamespaceResponse(
                    id=existing['id'],
                    namespace=existing['namespace'],
                    created_at=existing['created_at'].isoformat()
                )
            except Exception as e:
                logger.error(f"Error adding excluded namespace: {e}")
                raise

    async def remove_excluded_namespace(self, namespace: str) -> bool:
        """Remove a namespace from the exclusion list"""
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM excluded_namespaces WHERE namespace = $1",
                namespace
            )
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def get_excluded_namespaces(self) -> List[ExcludedNamespaceResponse]:
        """Get all excluded namespaces"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, namespace, created_at FROM excluded_namespaces ORDER BY namespace"
            )
            return [
                ExcludedNamespaceResponse(
                    id=row['id'],
                    namespace=row['namespace'],
                    created_at=row['created_at'].isoformat()
                )
                for row in rows
            ]

    async def is_namespace_excluded(self, namespace: str) -> bool:
        """Check if a namespace is in the exclusion list"""
        async with self._acquire() as conn:
            result = await conn.fetchrow(
                "SELECT 1 FROM excluded_namespaces WHERE namespace = $1",
                namespace
            )
            return result is not None

    async def get_all_namespaces(self) -> List[str]:
        """Get all unique namespaces from security findings and pod failures"""
        async with self._acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT namespace FROM (
                    SELECT namespace FROM security_findings WHERE dismissed = FALSE
                    UNION
                    SELECT namespace FROM pod_failures WHERE dismissed = FALSE
                ) AS all_namespaces
                ORDER BY namespace
            """)
            return [row['namespace'] for row in rows]

    async def delete_pod_failures_by_namespace(self, namespace: str) -> tuple[int, list]:
        """Delete all pod failures for a namespace and return deleted pods"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, pod_name, namespace FROM pod_failures
                   WHERE namespace = $1 AND dismissed = FALSE""",
                namespace
            )
            deleted_pods = [
                {'pod_name': row['pod_name'], 'namespace': row['namespace']}
                for row in rows
            ]

            result = await conn.execute(
                "DELETE FROM pod_failures WHERE namespace = $1",
                namespace
            )
            count = int(result.split()[-1]) if result else 0
            return count, deleted_pods

    # --- Excluded pods ---

    async def add_excluded_pod(self, pod_name: str) -> dict:
        """Add a pod to the monitoring exclusion list (by name only)"""
        async with self._acquire() as conn:
            try:
                result = await conn.fetchrow(
                    """INSERT INTO excluded_pods (pod_name)
                       VALUES ($1)
                       ON CONFLICT (pod_name) DO NOTHING
                       RETURNING id, pod_name, created_at""",
                    pod_name
                )
                if result:
                    return {
                        'id': result['id'],
                        'pod_name': result['pod_name'],
                        'created_at': result['created_at'].isoformat()
                    }
                existing = await conn.fetchrow(
                    "SELECT id, pod_name, created_at FROM excluded_pods WHERE pod_name = $1",
                    pod_name
                )
                return {
                    'id': existing['id'],
                    'pod_name': existing['pod_name'],
                    'created_at': existing['created_at'].isoformat()
                }
            except Exception as e:
                logger.error(f"Error adding excluded pod: {e}")
                raise

    async def remove_excluded_pod(self, pod_name: str) -> bool:
        """Remove a pod from the monitoring exclusion list"""
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM excluded_pods WHERE pod_name = $1",
                pod_name
            )
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def get_excluded_pods(self) -> List[dict]:
        """Get all excluded pods"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, pod_name, created_at FROM excluded_pods ORDER BY pod_name"
            )
            return [
                {
                    'id': row['id'],
                    'pod_name': row['pod_name'],
                    'created_at': row['created_at'].isoformat()
                }
                for row in rows
            ]

    async def is_pod_excluded(self, pod_name: str) -> bool:
        """Check if a pod is in the monitoring exclusion list (by name only)"""
        async with self._acquire() as conn:
            result = await conn.fetchrow(
                "SELECT 1 FROM excluded_pods WHERE pod_name = $1",
                pod_name
            )
            return result is not None

    async def get_all_monitored_pods(self) -> List[dict]:
        """Get all unique pod names from pod failures (for suggestions)"""
        async with self._acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT pod_name, namespace FROM pod_failures
                WHERE dismissed = FALSE
                ORDER BY pod_name
            """)
            return [{'pod_name': row['pod_name'], 'namespace': row['namespace']} for row in rows]

    async def delete_pod_failure_by_pod(self, pod_name: str) -> tuple[int, list]:
        """Delete pod failures for a specific pod name (across all namespaces)"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, pod_name, namespace FROM pod_failures
                   WHERE pod_name = $1 AND dismissed = FALSE""",
                pod_name
            )
            deleted_pods = [
                {'pod_name': row['pod_name'], 'namespace': row['namespace']}
                for row in rows
            ]

            result = await conn.execute(
                "DELETE FROM pod_failures WHERE pod_name = $1",
                pod_name
            )
            count = int(result.split()[-1]) if result else 0
            return count, deleted_pods

    # --- Excluded rules ---

    async def add_excluded_rule(self, rule_title: str, namespace: str = '') -> dict:
        """Add a rule to the security scan exclusion list (namespace='' for global)"""
        async with self._acquire() as conn:
            try:
                result = await conn.fetchrow(
                    """INSERT INTO excluded_rules (rule_title, namespace)
                       VALUES ($1, $2)
                       ON CONFLICT (rule_title, namespace) DO NOTHING
                       RETURNING id, rule_title, namespace, created_at""",
                    rule_title, namespace
                )
                if result:
                    return {
                        'id': result['id'],
                        'rule_title': result['rule_title'],
                        'namespace': result['namespace'] if result['namespace'] else None,
                        'created_at': result['created_at'].isoformat()
                    }
                existing = await conn.fetchrow(
                    "SELECT id, rule_title, namespace, created_at FROM excluded_rules WHERE rule_title = $1 AND namespace = $2",
                    rule_title, namespace
                )
                return {
                    'id': existing['id'],
                    'rule_title': existing['rule_title'],
                    'namespace': existing['namespace'] if existing['namespace'] else None,
                    'created_at': existing['created_at'].isoformat()
                }
            except Exception as e:
                logger.error(f"Error adding excluded rule: {e}")
                raise

    async def remove_excluded_rule(self, rule_title: str, namespace: str = '') -> bool:
        """Remove a rule from the exclusion list (namespace='' for global)"""
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM excluded_rules WHERE rule_title = $1 AND namespace = $2",
                rule_title, namespace
            )
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def get_excluded_rules(self) -> list:
        """Get all excluded rules"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, rule_title, namespace, created_at FROM excluded_rules ORDER BY rule_title, namespace"
            )
            return [
                {
                    'id': row['id'],
                    'rule_title': row['rule_title'],
                    'namespace': row['namespace'] if row['namespace'] else None,
                    'created_at': row['created_at'].isoformat()
                }
                for row in rows
            ]

    async def is_rule_excluded(self, rule_title: str, namespace: str = '') -> bool:
        """Check if a rule is excluded (globally or for a specific namespace).
        Supports base-name matching."""
        async with self._acquire() as conn:
            result = await conn.fetchrow(
                """SELECT 1 FROM excluded_rules
                   WHERE (namespace = '' OR namespace = $2)
                   AND (rule_title = $1 OR $1 LIKE rule_title || ': %')""",
                rule_title, namespace
            )
            return result is not None

    async def get_all_rule_titles(self, namespace: str = None) -> list:
        """Get all unique rule titles from security findings (for suggestions).
        Also includes base rule names for cluster-wide exclusion."""
        async with self._acquire() as conn:
            if namespace:
                rows = await conn.fetch("""
                    SELECT title FROM (
                        SELECT DISTINCT title FROM security_findings
                        WHERE dismissed = FALSE AND namespace = $1
                        UNION
                        SELECT DISTINCT split_part(title, ': ', 1) FROM security_findings
                        WHERE dismissed = FALSE AND namespace = $1 AND title LIKE '%: %'
                    ) sub
                    ORDER BY title
                """, namespace)
            else:
                rows = await conn.fetch("""
                    SELECT title FROM (
                        SELECT DISTINCT title FROM security_findings
                        WHERE dismissed = FALSE
                        UNION
                        SELECT DISTINCT split_part(title, ': ', 1) FROM security_findings
                        WHERE dismissed = FALSE AND title LIKE '%: %'
                    ) sub
                    ORDER BY title
                """)
            return [row['title'] for row in rows]

    # --- Trusted registries ---

    async def add_trusted_registry(self, registry: str) -> TrustedRegistryResponse:
        """Add a trusted container registry"""
        async with self._acquire() as conn:
            try:
                result = await conn.fetchrow(
                    """INSERT INTO trusted_registries (registry)
                       VALUES ($1)
                       ON CONFLICT (registry) DO NOTHING
                       RETURNING id, registry, created_at""",
                    registry
                )
                if result:
                    return TrustedRegistryResponse(
                        id=result['id'],
                        registry=result['registry'],
                        created_at=result['created_at'].isoformat()
                    )
                existing = await conn.fetchrow(
                    "SELECT id, registry, created_at FROM trusted_registries WHERE registry = $1",
                    registry
                )
                return TrustedRegistryResponse(
                    id=existing['id'],
                    registry=existing['registry'],
                    created_at=existing['created_at'].isoformat()
                )
            except Exception as e:
                logger.error(f"Error adding trusted registry: {e}")
                raise

    async def remove_trusted_registry(self, registry: str) -> bool:
        """Remove a trusted container registry"""
        async with self._acquire() as conn:
            result = await conn.execute(
                "DELETE FROM trusted_registries WHERE registry = $1",
                registry
            )
            count = int(result.split()[-1]) if result else 0
            return count > 0

    async def get_trusted_registries(self) -> list:
        """Get all admin-added trusted registries"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, registry, created_at FROM trusted_registries ORDER BY registry"
            )
            return [
                TrustedRegistryResponse(
                    id=row['id'],
                    registry=row['registry'],
                    created_at=row['created_at'].isoformat()
                )
                for row in rows
            ]
