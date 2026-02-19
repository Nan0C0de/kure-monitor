import logging
from typing import List, Optional
from models.models import SecurityFindingResponse

logger = logging.getLogger(__name__)


class SecurityFindingMixin:
    """Security finding CRUD methods. Requires self._acquire() and self._normalize_timestamp()."""

    async def save_security_finding(self, finding: SecurityFindingResponse) -> tuple[int, bool]:
        """Save a security finding to database.
        Returns (finding_id, is_new)."""
        async with self._acquire() as conn:
            timestamp = self._normalize_timestamp(finding.timestamp)

            existing = await conn.fetchrow("""
                SELECT id FROM security_findings
                WHERE resource_name = $1 AND namespace = $2 AND title = $3 AND dismissed = FALSE
                ORDER BY created_at DESC LIMIT 1
            """, finding.resource_name, finding.namespace, finding.title)

            if existing:
                await conn.execute("""
                    UPDATE security_findings SET
                        resource_type = $1, severity = $2, category = $3,
                        description = $4, remediation = $5, timestamp = $6,
                        manifest = $7
                    WHERE id = $8
                """,
                    finding.resource_type, finding.severity, finding.category,
                    finding.description, finding.remediation, timestamp,
                    finding.manifest, existing['id']
                )
                return existing['id'], False
            else:
                result = await conn.fetchrow("""
                    INSERT INTO security_findings (
                        resource_type, resource_name, namespace, severity, category,
                        title, description, remediation, timestamp, dismissed, manifest
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    RETURNING id
                """,
                    finding.resource_type, finding.resource_name, finding.namespace,
                    finding.severity, finding.category, finding.title,
                    finding.description, finding.remediation, timestamp, finding.dismissed,
                    finding.manifest
                )
                return result['id'], True

    async def get_security_findings(self, include_dismissed: bool = False, dismissed_only: bool = False) -> List[SecurityFindingResponse]:
        """Get all security findings from database"""
        async with self._acquire() as conn:
            query = "SELECT * FROM security_findings WHERE 1=1"

            if dismissed_only:
                query += " AND dismissed = TRUE"
            elif not include_dismissed:
                query += " AND dismissed = FALSE"

            query += " ORDER BY created_at DESC"

            rows = await conn.fetch(query)

            findings = []
            for row in rows:
                timestamp = row['timestamp'].isoformat()

                finding = SecurityFindingResponse(
                    id=row['id'],
                    resource_type=row['resource_type'],
                    resource_name=row['resource_name'],
                    namespace=row['namespace'],
                    severity=row['severity'],
                    category=row['category'],
                    title=row['title'],
                    description=row['description'],
                    remediation=row['remediation'],
                    timestamp=timestamp,
                    dismissed=bool(row['dismissed']),
                    manifest=row.get('manifest', '')
                )
                findings.append(finding)

            return findings

    async def get_security_finding_by_id(self, finding_id: int) -> Optional[SecurityFindingResponse]:
        """Get a single security finding by ID"""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM security_findings WHERE id = $1", finding_id
            )
            if not row:
                return None
            timestamp = row['timestamp'].isoformat()
            return SecurityFindingResponse(
                id=row['id'],
                resource_type=row['resource_type'],
                resource_name=row['resource_name'],
                namespace=row['namespace'],
                severity=row['severity'],
                category=row['category'],
                title=row['title'],
                description=row['description'],
                remediation=row['remediation'],
                timestamp=timestamp,
                dismissed=bool(row['dismissed']),
                manifest=row.get('manifest', '')
            )

    async def dismiss_security_finding(self, finding_id: int):
        """Mark a security finding as dismissed"""
        async with self._acquire() as conn:
            await conn.execute(
                "UPDATE security_findings SET dismissed = TRUE WHERE id = $1",
                finding_id
            )

    async def restore_security_finding(self, finding_id: int):
        """Restore a dismissed security finding"""
        async with self._acquire() as conn:
            await conn.execute(
                "UPDATE security_findings SET dismissed = FALSE WHERE id = $1",
                finding_id
            )

    async def clear_security_findings(self):
        """Clear all security findings (for new scans)"""
        async with self._acquire() as conn:
            await conn.execute("DELETE FROM security_findings WHERE dismissed = FALSE")

    async def delete_findings_by_resource(self, resource_type: str, namespace: str, resource_name: str) -> tuple[int, list]:
        """Delete all findings for a specific resource. Returns (count, deleted_findings)."""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                """SELECT resource_name, namespace, title FROM security_findings
                   WHERE resource_type = $1 AND namespace = $2 AND resource_name = $3""",
                resource_type, namespace, resource_name
            )
            deleted_findings = [
                {"resource_name": row['resource_name'], "namespace": row['namespace'], "title": row['title']}
                for row in rows
            ]

            result = await conn.execute(
                """DELETE FROM security_findings
                   WHERE resource_type = $1 AND namespace = $2 AND resource_name = $3""",
                resource_type, namespace, resource_name
            )
            count = int(result.split()[-1]) if result else 0
            return count, deleted_findings

    async def delete_findings_by_namespace(self, namespace: str) -> tuple[int, list]:
        """Delete all security findings for a namespace and return deleted findings"""
        async with self._acquire() as conn:
            rows = await conn.fetch(
                """SELECT id, resource_type, resource_name, namespace, severity, category,
                          title, description, remediation, timestamp
                   FROM security_findings WHERE namespace = $1 AND dismissed = FALSE""",
                namespace
            )
            deleted_findings = [
                {
                    'id': row['id'],
                    'resource_type': row['resource_type'],
                    'resource_name': row['resource_name'],
                    'namespace': row['namespace'],
                    'severity': row['severity'],
                    'category': row['category'],
                    'title': row['title'],
                    'description': row['description'],
                    'remediation': row['remediation'],
                    'timestamp': row['timestamp'].isoformat() if row['timestamp'] else None
                }
                for row in rows
            ]

            result = await conn.execute(
                "DELETE FROM security_findings WHERE namespace = $1",
                namespace
            )
            count = int(result.split()[-1]) if result else 0
            return count, deleted_findings

    async def delete_findings_by_rule_title(self, rule_title: str, namespace: str = None) -> tuple:
        """Delete security findings for a rule title. Supports base-name matching."""
        async with self._acquire() as conn:
            title_condition = "(title = $1 OR title LIKE $1 || ': %')"
            if namespace:
                rows = await conn.fetch(
                    f"""SELECT id, resource_type, resource_name, namespace, severity, category,
                              title, description, remediation, timestamp
                       FROM security_findings WHERE {title_condition} AND namespace = $2 AND dismissed = FALSE""",
                    rule_title, namespace
                )
            else:
                rows = await conn.fetch(
                    f"""SELECT id, resource_type, resource_name, namespace, severity, category,
                              title, description, remediation, timestamp
                       FROM security_findings WHERE {title_condition} AND dismissed = FALSE""",
                    rule_title
                )
            deleted_findings = [
                {
                    'id': row['id'],
                    'resource_type': row['resource_type'],
                    'resource_name': row['resource_name'],
                    'namespace': row['namespace'],
                    'severity': row['severity'],
                    'category': row['category'],
                    'title': row['title'],
                    'description': row['description'],
                    'remediation': row['remediation'],
                    'timestamp': row['timestamp'].isoformat() if row['timestamp'] else None
                }
                for row in rows
            ]

            if namespace:
                result = await conn.execute(
                    f"DELETE FROM security_findings WHERE {title_condition} AND namespace = $2",
                    rule_title, namespace
                )
            else:
                result = await conn.execute(
                    f"DELETE FROM security_findings WHERE {title_condition}",
                    rule_title
                )
            count = int(result.split()[-1]) if result else 0
            return count, deleted_findings
