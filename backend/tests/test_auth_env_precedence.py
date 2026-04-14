"""Unit tests for env-var precedence in auth resolvers.

These tests use a pure in-memory mock of the `app_settings` store so they
do not require a real PostgreSQL connection.
"""
import pytest

from api.auth import (
    SERVICE_TOKEN_SETTING_KEY,
    SESSION_SECRET_SETTING_KEY,
    get_service_token,
    get_session_secret,
    reset_auth_cache,
)


class FakeDB:
    """Minimal in-memory stand-in for the app_settings DB layer."""

    def __init__(self, initial: dict | None = None):
        self._settings: dict[str, str] = dict(initial or {})
        self.set_calls: list[tuple[str, str]] = []

    async def get_app_setting(self, key: str):
        return self._settings.get(key)

    async def set_app_setting(self, key: str, value: str):
        self._settings[key] = value
        self.set_calls.append((key, value))


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_auth_cache()
    yield
    reset_auth_cache()


# --- SERVICE_TOKEN ---------------------------------------------------------


@pytest.mark.asyncio
async def test_service_token_env_wins_over_empty_db(monkeypatch):
    """Env var set + empty DB: returns env value and seeds DB."""
    monkeypatch.setenv("SERVICE_TOKEN", "env-token-abc")
    db = FakeDB()

    result = await get_service_token(db)

    assert result == "env-token-abc"
    assert db._settings[SERVICE_TOKEN_SETTING_KEY] == "env-token-abc"
    assert (SERVICE_TOKEN_SETTING_KEY, "env-token-abc") in db.set_calls


@pytest.mark.asyncio
async def test_service_token_env_wins_and_overwrites_db(monkeypatch):
    """Env var set + DB has a different value: env wins, DB is overwritten."""
    monkeypatch.setenv("SERVICE_TOKEN", "env-token-abc")
    db = FakeDB({SERVICE_TOKEN_SETTING_KEY: "old-db-token"})

    result = await get_service_token(db)

    assert result == "env-token-abc"
    assert db._settings[SERVICE_TOKEN_SETTING_KEY] == "env-token-abc"
    assert (SERVICE_TOKEN_SETTING_KEY, "env-token-abc") in db.set_calls


@pytest.mark.asyncio
async def test_service_token_env_matches_db_no_rewrite(monkeypatch):
    """Env var matches DB: no redundant write."""
    monkeypatch.setenv("SERVICE_TOKEN", "same-token")
    db = FakeDB({SERVICE_TOKEN_SETTING_KEY: "same-token"})

    result = await get_service_token(db)

    assert result == "same-token"
    assert db.set_calls == []


@pytest.mark.asyncio
async def test_service_token_empty_env_falls_through_to_db(monkeypatch):
    """Empty env var is treated as unset; DB value wins."""
    monkeypatch.setenv("SERVICE_TOKEN", "")
    db = FakeDB({SERVICE_TOKEN_SETTING_KEY: "db-token"})

    result = await get_service_token(db)

    assert result == "db-token"
    assert db.set_calls == []


@pytest.mark.asyncio
async def test_service_token_no_env_no_db_generates(monkeypatch):
    """No env + no DB value: generate a new one and persist."""
    monkeypatch.delenv("SERVICE_TOKEN", raising=False)
    db = FakeDB()

    result = await get_service_token(db)

    assert result
    assert len(result) == 64  # secrets.token_hex(32) => 64 hex chars
    assert db._settings[SERVICE_TOKEN_SETTING_KEY] == result


# --- SESSION_SECRET --------------------------------------------------------


@pytest.mark.asyncio
async def test_session_secret_env_wins_and_overwrites_db(monkeypatch):
    """Same precedence applies to SESSION_SECRET."""
    monkeypatch.setenv("SESSION_SECRET", "env-secret-xyz")
    db = FakeDB({SESSION_SECRET_SETTING_KEY: "old-db-secret"})

    result = await get_session_secret(db)

    assert result == "env-secret-xyz"
    assert db._settings[SESSION_SECRET_SETTING_KEY] == "env-secret-xyz"
    assert (SESSION_SECRET_SETTING_KEY, "env-secret-xyz") in db.set_calls


@pytest.mark.asyncio
async def test_session_secret_env_seeds_empty_db(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "env-secret-xyz")
    db = FakeDB()

    result = await get_session_secret(db)

    assert result == "env-secret-xyz"
    assert db._settings[SESSION_SECRET_SETTING_KEY] == "env-secret-xyz"


@pytest.mark.asyncio
async def test_session_secret_cache_short_circuits_db(monkeypatch):
    """Once cached, further calls don't hit the DB."""
    monkeypatch.setenv("SESSION_SECRET", "env-secret-xyz")
    db = FakeDB()

    await get_session_secret(db)

    # Mutate the fake DB under us; cached value should still be returned.
    db._settings[SESSION_SECRET_SETTING_KEY] = "tampered"
    monkeypatch.delenv("SESSION_SECRET", raising=False)

    result = await get_session_secret(db)
    assert result == "env-secret-xyz"
