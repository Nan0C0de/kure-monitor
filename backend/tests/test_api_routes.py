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
    assert response.json() == []


@pytest.mark.asyncio
async def test_report_failed_pod(client: AsyncClient):
    """Test reporting a failed pod"""
    pod_data = {
        "pod_name": "test-pod",
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
    
    # Verify pod was stored
    response = await client.get("/api/pods/failed")
    assert response.status_code == 200
    pods = response.json()
    assert len(pods) == 1
    assert pods[0]["pod_name"] == "test-pod"
    assert pods[0]["failure_reason"] == "ImagePullBackOff"


@pytest.mark.asyncio
async def test_dismiss_failed_pod(client: AsyncClient):
    """Test dismissing a failed pod"""
    # First create a pod
    pod_data = {
        "pod_name": "test-pod-dismiss",
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
    
    await client.post("/api/pods/failed", json=pod_data)
    
    # Get the pod ID
    response = await client.get("/api/pods/failed")
    pods = response.json()
    pod_id = pods[0]["id"]
    
    # Dismiss the pod
    response = await client.delete(f"/api/pods/failed/{pod_id}")
    assert response.status_code == 200
    
    # Verify pod is dismissed
    response = await client.get("/api/pods/failed")
    pods = response.json()
    dismissed_pod = next(p for p in pods if p["id"] == pod_id)
    assert dismissed_pod["dismissed"] == True


@pytest.mark.asyncio
async def test_cluster_info_endpoint(client: AsyncClient):
    """Test cluster info endpoint"""
    response = await client.get("/api/cluster/info")
    assert response.status_code == 200
    data = response.json()
    assert "cluster_name" in data


@pytest.mark.asyncio
async def test_invalid_pod_data(client: AsyncClient):
    """Test reporting pod with invalid data"""
    invalid_pod_data = {
        "pod_name": "",  # Empty name should fail validation
        "namespace": "default"
    }
    
    response = await client.post("/api/pods/failed", json=invalid_pod_data)
    assert response.status_code == 422  # Validation error