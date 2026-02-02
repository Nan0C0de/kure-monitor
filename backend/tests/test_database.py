import pytest
from models.models import PodFailureResponse
from database.database import Database


@pytest.mark.asyncio
async def test_store_and_retrieve_pod_failure(test_db):
    """Test storing and retrieving pod failure"""
    pod_failure = PodFailureResponse(
        id=0,  # Will be set by database
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
        manifest="apiVersion: v1\nkind: Pod",
        solution="Test solution",
        timestamp="2025-01-01T00:00:00Z",
        dismissed=False
    )

    # Store pod failure
    stored_id = await test_db.save_pod_failure(pod_failure)
    assert stored_id is not None

    # Retrieve pod failures
    failures = await test_db.get_pod_failures()
    assert len(failures) >= 1

    # Find our failure
    failure = next((f for f in failures if f.pod_name == "test-pod"), None)
    assert failure is not None
    assert failure.pod_name == "test-pod"
    assert failure.failure_reason == "ImagePullBackOff"
    assert failure.solution == "Test solution"
    assert failure.dismissed == False


@pytest.mark.asyncio
async def test_dismiss_pod_failure(test_db):
    """Test dismissing a pod failure"""
    pod_failure = PodFailureResponse(
        id=0,
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
        manifest="apiVersion: v1\nkind: Pod",
        solution="Test solution",
        timestamp="2025-01-01T00:00:00Z",
        dismissed=False
    )

    # Store pod failure
    failure_id = await test_db.save_pod_failure(pod_failure)

    # Dismiss the failure
    await test_db.dismiss_pod_failure(failure_id)

    # Verify it's dismissed (include dismissed to find it)
    failures = await test_db.get_pod_failures(include_dismissed=True)
    failure = next((f for f in failures if f.id == failure_id), None)
    assert failure is not None
    assert failure.dismissed == True


@pytest.mark.asyncio
async def test_get_pod_failures_excludes_dismissed(test_db):
    """Test that get_pod_failures excludes dismissed pods by default"""
    # Create two pod failures with unique names
    import uuid
    unique_id = uuid.uuid4().hex[:8]

    pod_failure1 = PodFailureResponse(
        id=0,
        pod_name=f"pod-1-{unique_id}",
        namespace="default",
        node_name="test-node",
        phase="Pending",
        creation_timestamp="2025-01-01T00:00:00Z",
        failure_reason="ImagePullBackOff",
        failure_message="Failed to pull image",
        container_statuses=[],
        events=[],
        logs="",
        manifest="apiVersion: v1\nkind: Pod",
        solution="Solution 1",
        timestamp="2025-01-01T00:00:00Z",
        dismissed=False
    )

    pod_failure2 = PodFailureResponse(
        id=0,
        pod_name=f"pod-2-{unique_id}",
        namespace="default",
        node_name="test-node",
        phase="Pending",
        creation_timestamp="2025-01-01T00:00:00Z",
        failure_reason="CrashLoopBackOff",
        failure_message="Container crashed",
        container_statuses=[],
        events=[],
        logs="",
        manifest="apiVersion: v1\nkind: Pod",
        solution="Solution 2",
        timestamp="2025-01-01T00:00:00Z",
        dismissed=False
    )

    # Store both
    id1 = await test_db.save_pod_failure(pod_failure1)
    id2 = await test_db.save_pod_failure(pod_failure2)

    # Dismiss one
    await test_db.dismiss_pod_failure(id1)

    # Get active failures (should not include dismissed)
    failures = await test_db.get_pod_failures(include_dismissed=False)
    pod_names = [f.pod_name for f in failures]
    assert f"pod-1-{unique_id}" not in pod_names
    assert f"pod-2-{unique_id}" in pod_names

    # Get all failures (should return both)
    all_failures = await test_db.get_pod_failures(include_dismissed=True)
    all_pod_names = [f.pod_name for f in all_failures]
    assert f"pod-1-{unique_id}" in all_pod_names
    assert f"pod-2-{unique_id}" in all_pod_names
