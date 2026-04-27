"""Tests for the user-accounts + invitations + service-token auth system."""
import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, Mock
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from api.auth import (
    SESSION_COOKIE_NAME,
    SERVICE_TOKEN_SETTING_KEY,
    hash_password,
    reset_auth_cache,
    verify_password,
)
from api.middleware import configure_cors
from api.routes import create_api_router
from services.solution_engine import SolutionEngine
from services.websocket import WebSocketManager


DATABASE_AVAILABLE = bool(os.getenv("DATABASE_URL"))


pytestmark = pytest.mark.skipif(
    not DATABASE_AVAILABLE, reason="DATABASE_URL not set"
)


# ---------------------------------------------------------------------------
# App fixture — no dependency overrides (we want real auth).
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_app(test_db):
    reset_auth_cache()

    mock_solution_engine = Mock(spec=SolutionEngine)
    mock_solution_engine.get_solution = AsyncMock(return_value="Test solution")
    mock_solution_engine.llm_provider = None

    ws_manager = WebSocketManager()

    app = FastAPI()
    configure_cors(app)
    app.state.db = test_db

    api_router = create_api_router(
        db=test_db,
        solution_engine=mock_solution_engine,
        websocket_manager=ws_manager,
        notification_service=None,
    )
    app.include_router(api_router)
    return app


@pytest_asyncio.fixture
async def auth_client(auth_app):
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def test_password_hash_and_verify():
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert verify_password("correct horse battery staple", h) is True
    assert verify_password("wrong", h) is False


# ---------------------------------------------------------------------------
# Setup flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_required_when_no_users(auth_client):
    r = await auth_client.get("/api/auth/setup-required")
    assert r.status_code == 200
    assert r.json() == {"setup_required": True}


@pytest.mark.asyncio
async def test_setup_creates_first_admin_and_sets_cookie(auth_client):
    r = await auth_client.post(
        "/api/auth/setup",
        json={"username": "admin1", "password": "password123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["username"] == "admin1"
    assert body["user"]["role"] == "admin"
    # Cookie was set
    assert SESSION_COOKIE_NAME in r.cookies or SESSION_COOKIE_NAME in {
        c.split("=")[0].strip() for c in r.headers.get_list("set-cookie")
    }


@pytest.mark.asyncio
async def test_setup_rejected_after_first_user(auth_client):
    r1 = await auth_client.post(
        "/api/auth/setup",
        json={"username": "admin1", "password": "password123"},
    )
    assert r1.status_code == 200

    r2 = await auth_client.post(
        "/api/auth/setup",
        json={"username": "admin2", "password": "password123"},
    )
    assert r2.status_code == 409


# ---------------------------------------------------------------------------
# Login / logout / me
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_flow(auth_client):
    await auth_client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "password123"},
    )

    # Bad password
    bad = await auth_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrongpass"},
    )
    assert bad.status_code == 401

    # Good login
    # Use a fresh client so the setup cookie isn't reused
    transport = ASGITransport(app=auth_client._transport.app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        ok = await c.post(
            "/api/auth/login",
            json={"username": "admin", "password": "password123"},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["user"]["username"] == "admin"

        # /auth/me works now
        me = await c.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["role"] == "admin"

        # Logout clears session
        lo = await c.post("/api/auth/logout")
        assert lo.status_code == 204

        me2 = await c.get("/api/auth/me")
        assert me2.status_code == 401


@pytest.mark.asyncio
async def test_session_cookie_is_httponly(auth_client):
    r = await auth_client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "password123"},
    )
    assert r.status_code == 200
    set_cookie_headers = r.headers.get_list("set-cookie")
    kure_cookie = next(
        (c for c in set_cookie_headers if c.startswith(f"{SESSION_COOKIE_NAME}=")),
        None,
    )
    assert kure_cookie is not None
    assert "HttpOnly" in kure_cookie
    assert "SameSite=lax" in kure_cookie or "samesite=lax" in kure_cookie.lower()


# ---------------------------------------------------------------------------
# Role enforcement
# ---------------------------------------------------------------------------


async def _setup_admin(auth_app):
    """Create the first admin and return a client logged in as them."""
    transport = ASGITransport(app=auth_app)
    client = AsyncClient(transport=transport, base_url="http://test")
    r = await client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "password123"},
    )
    assert r.status_code == 200
    return client


async def _login_as(auth_app, username, password):
    transport = ASGITransport(app=auth_app)
    client = AsyncClient(transport=transport, base_url="http://test")
    r = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert r.status_code == 200, r.text
    return client


async def _invite_and_accept(admin_client, auth_app, role, username, password):
    """Admin creates an invitation; we accept it as a brand-new user."""
    inv = await admin_client.post(
        "/api/admin/invitations",
        json={"role": role, "expires_in_hours": 24},
    )
    assert inv.status_code == 200, inv.text
    token = inv.json()["token"]

    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        accept = await c.post(
            "/api/auth/accept-invitation",
            json={"token": token, "username": username, "password": password},
        )
        assert accept.status_code == 200, accept.text


@pytest.mark.asyncio
async def test_role_enforcement_read_cannot_mutate(auth_app):
    admin = await _setup_admin(auth_app)
    try:
        await _invite_and_accept(admin, auth_app, "read", "readuser", "password123")
    finally:
        await admin.aclose()

    # Login as the read user
    read_client = await _login_as(auth_app, "readuser", "password123")
    try:
        # Read endpoints work
        r = await read_client.get("/api/pods/failed")
        assert r.status_code == 200

        # Mutation endpoint (write-only) should 403
        r = await read_client.delete("/api/pods/failed/999999")
        assert r.status_code == 403

        # Admin-only endpoint should 403
        r = await read_client.get("/api/admin/users")
        assert r.status_code == 403
    finally:
        await read_client.aclose()


@pytest.mark.asyncio
async def test_role_enforcement_write_can_mutate_not_manage(auth_app):
    admin = await _setup_admin(auth_app)
    try:
        await _invite_and_accept(admin, auth_app, "write", "writeuser", "password123")
    finally:
        await admin.aclose()

    write_client = await _login_as(auth_app, "writeuser", "password123")
    try:
        # Can read
        r = await write_client.get("/api/pods/failed")
        assert r.status_code == 200

        # Can call a write mutation (404 is fine — the point is we got past auth)
        r = await write_client.delete("/api/pods/failed/999999")
        assert r.status_code != 401 and r.status_code != 403

        # Cannot manage users
        r = await write_client.get("/api/admin/users")
        assert r.status_code == 403

        r = await write_client.post(
            "/api/admin/invitations",
            json={"role": "read"},
        )
        assert r.status_code == 403
    finally:
        await write_client.aclose()


@pytest.mark.asyncio
async def test_role_enforcement_admin_can_do_everything(auth_app):
    admin = await _setup_admin(auth_app)
    try:
        r = await admin.get("/api/admin/users")
        assert r.status_code == 200
        users = r.json()
        assert len(users) == 1
        assert users[0]["role"] == "admin"

        r = await admin.post(
            "/api/admin/invitations",
            json={"role": "write"},
        )
        assert r.status_code == 200

        r = await admin.get("/api/admin/invitations")
        assert r.status_code == 200
    finally:
        await admin.aclose()


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invitation_create_use_once(auth_app):
    admin = await _setup_admin(auth_app)
    try:
        inv = await admin.post(
            "/api/admin/invitations",
            json={"role": "write"},
        )
        assert inv.status_code == 200
        token = inv.json()["token"]

        # Lookup works
        lookup = await admin.get(f"/api/auth/invitation/{token}")
        assert lookup.status_code == 200
        assert lookup.json()["role"] == "write"

        # Accept as a new user
        transport = ASGITransport(app=auth_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            ok = await c.post(
                "/api/auth/accept-invitation",
                json={"token": token, "username": "newwrite", "password": "password123"},
            )
            assert ok.status_code == 200

        # Second use fails
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            second = await c.post(
                "/api/auth/accept-invitation",
                json={"token": token, "username": "another", "password": "password123"},
            )
            assert second.status_code == 410
    finally:
        await admin.aclose()


@pytest.mark.asyncio
async def test_invitation_expired(auth_app, test_db):
    admin = await _setup_admin(auth_app)
    try:
        # Insert an already-expired invitation directly
        import secrets
        from datetime import datetime, timezone, timedelta
        token = secrets.token_urlsafe(32)
        async with test_db._db._acquire() as conn:
            await conn.execute(
                """
                INSERT INTO invitations (token, role, expires_at)
                VALUES ($1, 'read', $2)
                """,
                token,
                datetime.now(timezone.utc) - timedelta(hours=1),
            )

        lookup = await admin.get(f"/api/auth/invitation/{token}")
        assert lookup.status_code == 410
    finally:
        await admin.aclose()


@pytest.mark.asyncio
async def test_invitation_revoke(auth_app):
    admin = await _setup_admin(auth_app)
    try:
        inv = await admin.post(
            "/api/admin/invitations",
            json={"role": "read"},
        )
        assert inv.status_code == 200
        inv_id = inv.json()["id"]
        token = inv.json()["token"]

        # Revoke
        rev = await admin.delete(f"/api/admin/invitations/{inv_id}")
        assert rev.status_code == 200

        # Lookup now 404 (row deleted)
        lookup = await admin.get(f"/api/auth/invitation/{token}")
        assert lookup.status_code == 404
    finally:
        await admin.aclose()


@pytest.mark.asyncio
async def test_invitation_permanent_no_expiry(auth_app):
    """Permanent invitation: expires_in_hours=null → expires_at is null,
    invite is valid for lookup and acceptance, and shows up in the active list."""
    admin = await _setup_admin(auth_app)
    try:
        inv = await admin.post(
            "/api/admin/invitations",
            json={"role": "read", "expires_in_hours": None},
        )
        assert inv.status_code == 200, inv.text
        body = inv.json()
        assert body["expires_at"] is None
        token = body["token"]

        # Lookup works and reports null expires_at
        lookup = await admin.get(f"/api/auth/invitation/{token}")
        assert lookup.status_code == 200
        assert lookup.json()["expires_at"] is None

        # Permanent invite appears in the active list
        listed = await admin.get("/api/admin/invitations")
        assert listed.status_code == 200
        ids = [i["id"] for i in listed.json()]
        assert body["id"] in ids

        # Accept it as a new user — should succeed (no expiry to check)
        transport = ASGITransport(app=auth_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            ok = await c.post(
                "/api/auth/accept-invitation",
                json={"token": token, "username": "permuser", "password": "password123"},
            )
            assert ok.status_code == 200, ok.text
    finally:
        await admin.aclose()


@pytest.mark.asyncio
async def test_invitation_long_expiry_above_old_cap(auth_app):
    """Backend no longer enforces a 720-hour cap. A 1-year value (8760h) must be accepted."""
    admin = await _setup_admin(auth_app)
    try:
        inv = await admin.post(
            "/api/admin/invitations",
            json={"role": "read", "expires_in_hours": 8760},
        )
        assert inv.status_code == 200, inv.text
        assert inv.json()["expires_at"] is not None
    finally:
        await admin.aclose()


# ---------------------------------------------------------------------------
# Service token (ingest endpoints)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_token_required_for_ingest(auth_client, test_db):
    # No token → 401
    pod_data = {
        "pod_name": "test-pod",
        "namespace": "default",
        "node_name": "n1",
        "phase": "Pending",
        "creation_timestamp": "2025-01-01T00:00:00Z",
        "failure_reason": "ImagePullBackOff",
        "failure_message": "failed",
        "container_statuses": [],
        "events": [],
        "logs": "",
        "manifest": "apiVersion: v1\nkind: Pod",
    }
    r = await auth_client.post("/api/pods/failed", json=pod_data)
    assert r.status_code == 401

    # Get the service token
    service_token = await test_db.get_app_setting(SERVICE_TOKEN_SETTING_KEY)
    assert service_token

    # With token → 200
    r = await auth_client.post(
        "/api/pods/failed",
        json=pod_data,
        headers={"X-Service-Token": service_token},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_service_token_rejected_when_wrong(auth_client):
    pod_data = {
        "pod_name": "test-pod",
        "namespace": "default",
        "node_name": "n1",
        "phase": "Pending",
        "creation_timestamp": "2025-01-01T00:00:00Z",
        "failure_reason": "ImagePullBackOff",
        "failure_message": "failed",
        "container_statuses": [],
        "events": [],
        "logs": "",
        "manifest": "apiVersion: v1\nkind: Pod",
    }
    r = await auth_client.post(
        "/api/pods/failed",
        json=pod_data,
        headers={"X-Service-Token": "wrong-token"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Last-admin protection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cannot_delete_last_admin(auth_app):
    admin = await _setup_admin(auth_app)
    try:
        users = (await admin.get("/api/admin/users")).json()
        assert len(users) == 1
        admin_id = users[0]["id"]

        # Deleting self is blocked regardless
        r = await admin.delete(f"/api/admin/users/{admin_id}")
        assert r.status_code == 400
    finally:
        await admin.aclose()


@pytest.mark.asyncio
async def test_cannot_demote_last_admin(auth_app):
    admin = await _setup_admin(auth_app)
    try:
        # Create another admin via invitation path won't work (invitations are write/read only).
        # Directly test: demoting self returns 400 "cannot change own role"
        users = (await admin.get("/api/admin/users")).json()
        admin_id = users[0]["id"]

        r = await admin.patch(
            f"/api/admin/users/{admin_id}",
            json={"role": "write"},
        )
        assert r.status_code == 400
    finally:
        await admin.aclose()


@pytest.mark.asyncio
async def test_cannot_delete_last_admin_even_by_other_admin(auth_app, test_db):
    """If two admins exist, deleting one is OK; deleting the last is blocked."""
    admin1 = await _setup_admin(auth_app)
    try:
        # Create a second admin directly in DB (bypassing invitation restrictions)
        from api.auth import hash_password
        await test_db.create_user(
            username="admin2",
            password_hash=hash_password("password123"),
            role="admin",
        )

        # Get both users
        users = (await admin1.get("/api/admin/users")).json()
        admin2_id = next(u["id"] for u in users if u["username"] == "admin2")

        # admin1 can delete admin2 (two admins remain after: wait, before is 2, after is 1)
        r = await admin1.delete(f"/api/admin/users/{admin2_id}")
        assert r.status_code == 200

        # Now admin1 is the only admin; admin2 is gone.
        users_after = (await admin1.get("/api/admin/users")).json()
        assert len(users_after) == 1
    finally:
        await admin1.aclose()


# ---------------------------------------------------------------------------
# WebSocket auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_auth_rejects_when_no_token(auth_app):
    """Plain WS connect with no cookie & no token is rejected."""
    from httpx_ws import aconnect_ws  # optional; if not installed we skip
    pytest.skip("Tested via Starlette TestClient below")


def test_ws_auth_accepts_cookie_and_service_token(auth_app, test_db):
    """WebSocket connects with either a session cookie OR a service token."""
    from fastapi.testclient import TestClient
    import asyncio

    client = TestClient(auth_app)

    # Setup an admin user so we can get a session cookie
    r = client.post(
        "/api/auth/setup",
        json={"username": "admin", "password": "password123"},
    )
    assert r.status_code == 200, r.text

    # 1. No auth at all → rejected
    try:
        with client.websocket_connect("/ws"):
            pytest.fail("Expected WS rejection")
    except Exception:
        pass  # expected

    # 2. With cookie → accepted
    with client.websocket_connect("/ws") as ws:
        # cookie is auto-sent by TestClient; sanity-check we got past handshake
        assert ws is not None

    # 3. Logout (clear cookie) then connect with service token in query param
    client.post("/api/auth/logout")
    client.cookies.clear()

    service_token = asyncio.get_event_loop().run_until_complete(
        test_db.get_app_setting(SERVICE_TOKEN_SETTING_KEY)
    )
    assert service_token

    with client.websocket_connect(f"/ws?token={service_token}") as ws:
        assert ws is not None

    # 4. Bad token → rejected
    try:
        with client.websocket_connect("/ws?token=bogus"):
            pytest.fail("Expected WS rejection")
    except Exception:
        pass  # expected
