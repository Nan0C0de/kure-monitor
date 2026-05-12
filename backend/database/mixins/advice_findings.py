"""AI Advice findings persistence mixin.

Mirrors :class:`SecurityFindingMixin` but is keyed on the
``(detector_id, namespace, resource_kind, resource_name)`` tuple. Stores
the structured ``evidence`` dict in a JSONB column.

Upsert semantics
----------------
* If a NON-dismissed row already exists for the key tuple, it is updated
  in place and returned as ``is_new=False``.
* If the existing row is ``dismissed=TRUE``, a new row is inserted so
  the dismissed history is preserved and the fresh instance can be
  surfaced again. ``is_new=True``.

``clear_advice_findings_for_scope`` deletes only NON-dismissed rows in
the given scope; the engine calls it at the start of a scan so stale
findings don't accumulate while dismissed history is preserved.
"""

import json
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> dict:
    """Convert a database row into a JSON-friendly dict matching the
    :class:`models.models.AdviceFinding` shape (plus ``id`` and
    ``dismissed``/``created_at`` bookkeeping)."""
    evidence = row["evidence"]
    # asyncpg returns JSONB as the parsed Python type already (dict/list);
    # if it ever comes back as a string, parse it defensively.
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except (TypeError, ValueError):
            evidence = {}
    created_at = row["created_at"]
    return {
        "id": row["id"],
        "detector_id": row["detector_id"],
        "severity": row["severity"],
        "category": row["category"],
        "title": row["title"],
        "summary": row["summary"],
        "resource_kind": row["resource_kind"],
        "resource_name": row["resource_name"],
        "namespace": row["namespace"],
        "evidence": evidence or {},
        "recommended_change": row["recommended_change"],
        "confidence": (
            float(row["confidence"]) if row["confidence"] is not None else 0.0
        ),
        "explanation": row["explanation"],
        "dismissed": bool(row["dismissed"]),
        "created_at": created_at.isoformat() if created_at else None,
    }


class AdviceFindingMixin:
    """Advice finding CRUD methods. Requires self._acquire()."""

    async def save_advice_finding(self, finding_dict: dict) -> tuple[int, bool]:
        """Upsert an advice finding.

        Returns ``(finding_id, is_new)``. See module docstring for the
        upsert rules.
        """
        async with self._acquire() as conn:
            evidence_json = json.dumps(finding_dict.get("evidence") or {})

            existing = await conn.fetchrow(
                """
                SELECT id FROM advice_findings
                WHERE detector_id = $1
                  AND namespace = $2
                  AND resource_kind = $3
                  AND resource_name = $4
                  AND dismissed = FALSE
                ORDER BY created_at DESC LIMIT 1
                """,
                finding_dict["detector_id"],
                finding_dict["namespace"],
                finding_dict["resource_kind"],
                finding_dict["resource_name"],
            )

            if existing:
                await conn.execute(
                    """
                    UPDATE advice_findings SET
                        severity = $1,
                        category = $2,
                        title = $3,
                        summary = $4,
                        evidence = $5::jsonb,
                        recommended_change = $6,
                        confidence = $7,
                        explanation = $8
                    WHERE id = $9
                    """,
                    finding_dict["severity"],
                    finding_dict["category"],
                    finding_dict["title"],
                    finding_dict["summary"],
                    evidence_json,
                    finding_dict["recommended_change"],
                    float(finding_dict["confidence"]),
                    finding_dict.get("explanation"),
                    existing["id"],
                )
                return existing["id"], False

            result = await conn.fetchrow(
                """
                INSERT INTO advice_findings (
                    detector_id, severity, category, title, summary,
                    resource_kind, resource_name, namespace,
                    evidence, recommended_change, confidence, explanation,
                    dismissed
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, FALSE)
                RETURNING id
                """,
                finding_dict["detector_id"],
                finding_dict["severity"],
                finding_dict["category"],
                finding_dict["title"],
                finding_dict["summary"],
                finding_dict["resource_kind"],
                finding_dict["resource_name"],
                finding_dict["namespace"],
                evidence_json,
                finding_dict["recommended_change"],
                float(finding_dict["confidence"]),
                finding_dict.get("explanation"),
            )
            return result["id"], True

    async def get_advice_findings(
        self,
        include_dismissed: bool = False,
        dismissed_only: bool = False,
        namespace: Optional[str] = None,
        resource_kind: Optional[str] = None,
        resource_name: Optional[str] = None,
    ) -> List[dict]:
        """Fetch advice findings with optional scope/dismissed filters."""
        async with self._acquire() as conn:
            clauses = ["1=1"]
            args: list = []

            if dismissed_only:
                clauses.append("dismissed = TRUE")
            elif not include_dismissed:
                clauses.append("dismissed = FALSE")

            if namespace is not None:
                args.append(namespace)
                clauses.append(f"namespace = ${len(args)}")
            if resource_kind is not None:
                args.append(resource_kind)
                clauses.append(f"resource_kind = ${len(args)}")
            if resource_name is not None:
                args.append(resource_name)
                clauses.append(f"resource_name = ${len(args)}")

            query = (
                "SELECT * FROM advice_findings WHERE "
                + " AND ".join(clauses)
                + " ORDER BY created_at DESC"
            )
            rows = await conn.fetch(query, *args)
            return [_row_to_dict(r) for r in rows]

    async def get_advice_finding_by_id(self, finding_id: int) -> Optional[dict]:
        """Fetch a single advice finding by id, or ``None`` if missing."""
        async with self._acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM advice_findings WHERE id = $1", finding_id
            )
            if not row:
                return None
            return _row_to_dict(row)

    async def dismiss_advice_finding(self, finding_id: int) -> bool:
        """Mark an advice finding as dismissed. Returns True if a row was updated."""
        async with self._acquire() as conn:
            result = await conn.execute(
                "UPDATE advice_findings SET dismissed = TRUE WHERE id = $1 AND dismissed = FALSE",
                finding_id,
            )
            # asyncpg returns "UPDATE <count>"; count==0 if no row matched.
            try:
                count = int(result.split()[-1])
            except (ValueError, IndexError):
                count = 0
            return count > 0

    async def restore_advice_finding(self, finding_id: int) -> bool:
        """Restore a dismissed advice finding. Returns True if a row was updated."""
        async with self._acquire() as conn:
            result = await conn.execute(
                "UPDATE advice_findings SET dismissed = FALSE WHERE id = $1 AND dismissed = TRUE",
                finding_id,
            )
            try:
                count = int(result.split()[-1])
            except (ValueError, IndexError):
                count = 0
            return count > 0

    async def clear_advice_findings_for_scope(
        self,
        namespace: Optional[str] = None,
        resource_kind: Optional[str] = None,
        resource_name: Optional[str] = None,
    ) -> int:
        """Delete NON-dismissed advice findings matching the given scope.

        Called at the start of a scan so stale findings disappear when the
        underlying manifests have been fixed. Dismissed history is preserved.

        Returns the number of rows deleted.
        """
        async with self._acquire() as conn:
            clauses = ["dismissed = FALSE"]
            args: list = []
            if namespace is not None:
                args.append(namespace)
                clauses.append(f"namespace = ${len(args)}")
            if resource_kind is not None:
                args.append(resource_kind)
                clauses.append(f"resource_kind = ${len(args)}")
            if resource_name is not None:
                args.append(resource_name)
                clauses.append(f"resource_name = ${len(args)}")
            query = "DELETE FROM advice_findings WHERE " + " AND ".join(clauses)
            result = await conn.execute(query, *args)
            try:
                return int(result.split()[-1])
            except (ValueError, IndexError):
                return 0
