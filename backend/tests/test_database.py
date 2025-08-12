import pytest
from database.database import Database
from models.models import PodFailureCreate


@pytest.mark.asyncio
async def test_store_and_retrieve_pod_failure(test_db):
    """Test storing and retrieving pod failure"""
    pod_failure = PodFailureCreate(
        pod_name="test-pod",
        namespace="default",
        node_name="test-node",
        phase="Pending",
        creation_timestamp="2025-01-01T00:00:00Z",
        failure_reason="ImagePullBackOff",
        failure_message="Failed to pull image",
        container_statuses=[],
        events=[],
        logs="",
        manifest="apiVersion: v1\nkind: Pod"
    )
    
    # Store pod failure
    stored_id = await test_db.store_pod_failure(pod_failure, "Test solution")
    assert stored_id is not None
    
    # Retrieve pod failures
    failures = await test_db.get_pod_failures()
    assert len(failures) == 1
    
    failure = failures[0]
    assert failure["pod_name"] == "test-pod"
    assert failure["failure_reason"] == "ImagePullBackOff"
    assert failure["solution"] == "Test solution"
    assert failure["dismissed"] == False


@pytest.mark.asyncio
async def test_dismiss_pod_failure(test_db):
    """Test dismissing a pod failure"""
    pod_failure = PodFailureCreate(
        pod_name="test-pod-dismiss",
        namespace="default",
        node_name="test-node",
        phase="Pending",
        creation_timestamp="2025-01-01T00:00:00Z",
        failure_reason="ImagePullBackOff",
        failure_message="Failed to pull image",
        container_statuses=[],
        events=[],
        logs="",
        manifest="apiVersion: v1\nkind: Pod"
    )
    
    # Store pod failure
    failure_id = await test_db.store_pod_failure(pod_failure, "Test solution")
    
    # Dismiss the failure
    success = await test_db.dismiss_pod_failure(failure_id)
    assert success == True
    
    # Verify it's dismissed
    failures = await test_db.get_pod_failures()
    failure = failures[0]
    assert failure["dismissed"] == True


@pytest.mark.asyncio
async def test_get_pod_failures_excludes_dismissed(test_db):
    """Test that get_pod_failures excludes dismissed pods by default"""
    # Create two pod failures
    pod_failure1 = PodFailureCreate(
        pod_name="pod-1",
        namespace="default",
        node_name="test-node",
        phase="Pending",
        creation_timestamp="2025-01-01T00:00:00Z",
        failure_reason="ImagePullBackOff",
        failure_message="Failed to pull image",
        container_statuses=[],
        events=[],
        logs="",
        manifest="apiVersion: v1\nkind: Pod"
    )
    
    pod_failure2 = PodFailureCreate(
        pod_name="pod-2",
        namespace="default",
        node_name="test-node",
        phase="Pending",
        creation_timestamp="2025-01-01T00:00:00Z",
        failure_reason="CrashLoopBackOff",
        failure_message="Container crashed",
        container_statuses=[],
        events=[],
        logs="",
        manifest="apiVersion: v1\nkind: Pod"
    )
    
    # Store both
    id1 = await test_db.store_pod_failure(pod_failure1, "Solution 1")
    id2 = await test_db.store_pod_failure(pod_failure2, "Solution 2")
    
    # Dismiss one
    await test_db.dismiss_pod_failure(id1)
    
    # Get active failures (should only return non-dismissed)
    failures = await test_db.get_pod_failures(include_dismissed=False)
    assert len(failures) == 1
    assert failures[0]["pod_name"] == "pod-2"
    
    # Get all failures (should return both)
    all_failures = await test_db.get_pod_failures(include_dismissed=True)
    assert len(all_failures) == 2