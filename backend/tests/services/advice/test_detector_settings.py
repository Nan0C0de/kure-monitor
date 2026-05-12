"""Tests for ``DetectorSettingsService``."""

from __future__ import annotations

import json

import pytest

from services.advice.detector_settings import DetectorSettingsService


class _FakeDB:
    """In-memory stand-in for the AppSettings mixin methods."""

    def __init__(self) -> None:
        self._kv: dict = {}
        self.get_calls = 0
        self.set_calls = 0

    async def get_app_setting(self, key: str):
        self.get_calls += 1
        return self._kv.get(key)

    async def set_app_setting(self, key: str, value: str):
        self.set_calls += 1
        self._kv[key] = value


@pytest.mark.asyncio
async def test_get_all_empty_when_unset():
    svc = DetectorSettingsService(_FakeDB())
    assert await svc.get_all() == {}


@pytest.mark.asyncio
async def test_is_enabled_default_true_for_unknown():
    svc = DetectorSettingsService(_FakeDB())
    assert await svc.is_enabled("foo-detector") is True


@pytest.mark.asyncio
async def test_set_then_get():
    db = _FakeDB()
    svc = DetectorSettingsService(db)
    await svc.set_enabled("foo", False)
    assert await svc.is_enabled("foo") is False
    assert await svc.is_enabled("bar") is True  # default

    # Check the wire-stored value is a JSON object.
    stored = db._kv[DetectorSettingsService.SETTING_KEY]
    assert json.loads(stored) == {"foo": False}


@pytest.mark.asyncio
async def test_ttl_cache_invalidates_on_set():
    db = _FakeDB()
    svc = DetectorSettingsService(db)

    # First read populates the cache.
    await svc.get_all()
    assert db.get_calls == 1

    # Subsequent read within TTL hits cache.
    await svc.get_all()
    assert db.get_calls == 1

    # set_enabled reads (to merge) and invalidates the cache; the next
    # get_all triggers another DB read.
    await svc.set_enabled("a", True)
    await svc.get_all()
    # Two more get_app_setting calls: one inside set_enabled, one for the
    # next get_all.
    assert db.get_calls >= 3


@pytest.mark.asyncio
async def test_malformed_value_yields_empty_map():
    db = _FakeDB()
    db._kv[DetectorSettingsService.SETTING_KEY] = "not json {"
    svc = DetectorSettingsService(db)
    assert await svc.get_all() == {}


@pytest.mark.asyncio
async def test_set_preserves_other_entries():
    db = _FakeDB()
    db._kv[DetectorSettingsService.SETTING_KEY] = json.dumps({"a": True, "b": False})
    svc = DetectorSettingsService(db)
    await svc.set_enabled("c", False)
    stored = json.loads(db._kv[DetectorSettingsService.SETTING_KEY])
    assert stored == {"a": True, "b": False, "c": False}
