import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class KyvernoMixin:
    """Kyverno policy CRUD. Requires self._acquire()."""

    def _row_to_kyverno_policy(self, row) -> dict:
        """Convert a database row to a Kyverno policy dict."""
        excluded_ns = row['excluded_namespaces']
        excluded_deploy = row['excluded_deployments']
        if isinstance(excluded_ns, str):
            excluded_ns = json.loads(excluded_ns)
        if isinstance(excluded_deploy, str):
            excluded_deploy = json.loads(excluded_deploy)

        return {
            'id': row['id'],
            'policy_id': row['policy_id'],
            'display_name': row['display_name'],
            'category': row['category'],
            'description': row['description'],
            'severity': row['severity'],
            'enabled': row['enabled'],
            'mode': row['mode'],
            'excluded_namespaces': excluded_ns or [],
            'excluded_deployments': excluded_deploy or [],
            'synced': row['synced'],
            'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
        }

    async def seed_kyverno_policies(self, policies: list):
        """Upsert policy definitions from registry. Preserves user config on upgrade."""
        async with self._acquire() as conn:
            for policy in policies:
                await conn.execute("""
                    INSERT INTO kyverno_policies (policy_id, display_name, category, description, severity)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (policy_id) DO UPDATE
                    SET display_name = $2, category = $3, description = $4, severity = $5
                """, policy['policy_id'], policy['display_name'], policy['category'],
                    policy['description'], policy.get('severity', 'medium'))

    async def get_kyverno_policies(self) -> list:
        """Get all Kyverno policies with their configuration."""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM kyverno_policies ORDER BY category, display_name"
            )
            return [self._row_to_kyverno_policy(row) for row in rows]

    async def get_kyverno_policy(self, policy_id: str) -> Optional[dict]:
        """Get a single Kyverno policy by its policy_id."""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM kyverno_policies WHERE policy_id = $1", policy_id
            )
            return self._row_to_kyverno_policy(row) if row else None

    async def update_kyverno_policy(self, policy_id: str, config: dict) -> Optional[dict]:
        """Update policy config (enabled, mode, exclusions). Sets synced=False."""
        async with self._acquire() as conn:
            excluded_ns = json.dumps(config.get('excluded_namespaces', []))
            excluded_deploy = json.dumps(config.get('excluded_deployments', []))
            row = await conn.fetchrow("""
                UPDATE kyverno_policies
                SET enabled = $2, mode = $3, excluded_namespaces = $4,
                    excluded_deployments = $5, synced = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE policy_id = $1
                RETURNING *
            """, policy_id, config.get('enabled', False), config.get('mode', 'audit'),
                excluded_ns, excluded_deploy)
            return self._row_to_kyverno_policy(row) if row else None

    async def set_kyverno_policy_synced(self, policy_id: str, synced: bool):
        """Mark a policy as synced (or not) with the cluster."""
        async with self._acquire() as conn:
            await conn.execute(
                "UPDATE kyverno_policies SET synced = $2 WHERE policy_id = $1",
                policy_id, synced
            )

    async def get_enabled_kyverno_policies(self) -> list:
        """Get all enabled Kyverno policies (for reconciliation)."""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM kyverno_policies WHERE enabled = TRUE"
            )
            return [self._row_to_kyverno_policy(row) for row in rows]
