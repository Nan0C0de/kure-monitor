"""Persistence layer for per-detector enable/disable flags.

Stores a single row in the ``app_settings`` table under the key
``advice_detector_enabled``; the value is a JSON object mapping
``detector_id -> bool``. Missing entries default to ``True`` (enabled).

A tiny per-instance TTL cache keeps the read-heavy AdviceEngine path
from hitting the DB on every scan. ``set_enabled`` invalidates the cache.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

#: Cache lifetime for the in-memory copy of the settings row.
_CACHE_TTL_SECONDS: float = 60.0


class DetectorSettingsService:
    """Reads/writes the ``advice_detector_enabled`` app setting."""

    SETTING_KEY: str = "advice_detector_enabled"

    def __init__(self, db: Any):
        self.db = db
        self._cache: Dict[str, bool] = {}
        self._cache_expires_at: float = 0.0

    async def get_all(self) -> Dict[str, bool]:
        """Return the full ``{detector_id: enabled}`` map.

        Uses an in-memory TTL cache; falls back to ``{}`` on any read /
        parse error so a transient DB blip doesn't disable detectors.
        """
        now = time.monotonic()
        if now < self._cache_expires_at:
            return dict(self._cache)

        try:
            raw = await self.db.get_app_setting(self.SETTING_KEY)
        except Exception:
            logger.exception(
                "DetectorSettingsService: get_app_setting failed; "
                "returning empty map (all detectors default to enabled)."
            )
            return {}

        parsed: Dict[str, bool] = {}
        if raw:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    for k, v in loaded.items():
                        if isinstance(k, str) and isinstance(v, bool):
                            parsed[k] = v
            except (TypeError, ValueError):
                logger.warning(
                    "DetectorSettingsService: malformed JSON in app_settings[%s]; "
                    "ignoring.",
                    self.SETTING_KEY,
                )

        self._cache = parsed
        self._cache_expires_at = now + _CACHE_TTL_SECONDS
        return dict(parsed)

    async def is_enabled(self, detector_id: str) -> bool:
        """Default to ``True`` when the detector has no explicit entry."""
        settings = await self.get_all()
        return settings.get(detector_id, True)

    async def set_enabled(self, detector_id: str, enabled: bool) -> None:
        """Upsert the flag and invalidate the cache."""
        # Always read the freshest value from the DB to avoid clobbering a
        # concurrent writer's change with our stale cache.
        try:
            raw = await self.db.get_app_setting(self.SETTING_KEY)
        except Exception:
            raw = None
        current: Dict[str, bool] = {}
        if raw:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    for k, v in loaded.items():
                        if isinstance(k, str) and isinstance(v, bool):
                            current[k] = v
            except (TypeError, ValueError):
                current = {}

        current[detector_id] = enabled
        await self.db.set_app_setting(self.SETTING_KEY, json.dumps(current))

        # Invalidate cache so the next read picks up the new value.
        self._cache = {}
        self._cache_expires_at = 0.0
