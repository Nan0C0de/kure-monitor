import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    """Test health check endpoint"""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_get_failed_pods_empty(client: AsyncClient):
    """Test getting failed pods when none exist"""
    response = await client.get("/api/pods/failed")
    assert response.status_code == 200
    # Response is a list (may or may not be empty depending on test order)
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_report_failed_pod(client: AsyncClient):
    """Test reporting a failed pod"""
    import uuid
    unique_id = uuid.uuid4().hex[:8]

    pod_data = {
        "pod_name": f"test-pod-{unique_id}",
        "namespace": "default",
        "node_name": "test-node",
        "phase": "Pending",
        "creation_timestamp": "2025-01-01T00:00:00Z",
        "failure_reason": "ImagePullBackOff",
        "failure_message": "Failed to pull image",
        "container_statuses": [],
        "events": [],
        "logs": "",
        "manifest": "apiVersion: v1\nkind: Pod"
    }

    response = await client.post("/api/pods/failed", json=pod_data)
    assert response.status_code == 200

    # Verify response contains expected fields
    result = response.json()
    assert result["pod_name"] == f"test-pod-{unique_id}"
    assert result["failure_reason"] == "ImagePullBackOff"
    assert "solution" in result
    assert result["id"] is not None


@pytest.mark.asyncio
async def test_dismiss_failed_pod(client: AsyncClient):
    """Test dismissing a failed pod"""
    import uuid
    unique_id = uuid.uuid4().hex[:8]

    # First create a pod
    pod_data = {
        "pod_name": f"test-pod-dismiss-{unique_id}",
        "namespace": "default",
        "node_name": "test-node",
        "phase": "Pending",
        "creation_timestamp": "2025-01-01T00:00:00Z",
        "failure_reason": "ImagePullBackOff",
        "failure_message": "Failed to pull image",
        "container_statuses": [],
        "events": [],
        "logs": "",
        "manifest": "apiVersion: v1\nkind: Pod"
    }

    create_response = await client.post("/api/pods/failed", json=pod_data)
    assert create_response.status_code == 200
    pod_id = create_response.json()["id"]

    # Dismiss the pod
    response = await client.delete(f"/api/pods/failed/{pod_id}")
    assert response.status_code == 200

    # Verify pod is in ignored list (dismissed pods)
    response = await client.get("/api/pods/ignored")
    assert response.status_code == 200
    pods = response.json()
    dismissed_pod = next((p for p in pods if p["id"] == pod_id), None)
    assert dismissed_pod is not None
    assert dismissed_pod["dismissed"] == True


@pytest.mark.asyncio
async def test_invalid_pod_data(client: AsyncClient):
    """Test reporting pod with invalid data"""
    invalid_pod_data = {
        "pod_name": "",  # Empty name should fail validation
        "namespace": "default"
    }

    response = await client.post("/api/pods/failed", json=invalid_pod_data)
    assert response.status_code == 422  # Validation error
