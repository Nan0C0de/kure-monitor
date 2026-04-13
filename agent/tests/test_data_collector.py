import base64
import gzip
import pytest
from unittest.mock import Mock, AsyncMock
from kubernetes.client.rest import ApiException
from services.data_collector import DataCollector, MAX_RAW_BYTES


class TestDataCollector:
    
    @pytest.fixture
    def data_collector(self):
        """Create DataCollector instance"""
        return DataCollector()

    @pytest.fixture
    def mock_pod(self):
        """Create a mock pod"""
        pod = Mock()
        pod.metadata.name = "test-pod"
        pod.metadata.namespace = "default"
        pod.metadata.creation_timestamp.isoformat.return_value = "2025-01-01T00:00:00Z"
        pod.spec.node_name = "test-node"
        pod.status.phase = "Pending"
        pod.status.container_statuses = [Mock()]
        
        container_status = pod.status.container_statuses[0]
        container_status.name = "test-container"
        container_status.ready = False
        container_status.restart_count = 0
        container_status.image = "test:latest"
        container_status.state.waiting = Mock()
        container_status.state.waiting.reason = "ImagePullBackOff"
        container_status.state.waiting.message = "Failed to pull image"
        container_status.state.running = None
        container_status.state.terminated = None
        
        return pod

    @pytest.fixture
    def mock_v1_client(self):
        """Create mock Kubernetes v1 client"""
        client = Mock()

        # Mock events - use ImagePullBackOff to match expected test results
        events = Mock()
        events.items = [Mock()]
        event = events.items[0]
        event.type = "Warning"
        event.reason = "ImagePullBackOff"
        event.message = "Failed to pull image"
        event.first_timestamp = Mock()
        event.first_timestamp.isoformat.return_value = "2025-01-01T00:00:00Z"

        client.list_namespaced_event.return_value = events

        # Mock logs (will fail with 403)
        from kubernetes.client.rest import ApiException
        client.read_namespaced_pod_log.side_effect = ApiException(status=403, reason="Forbidden")

        return client

    @pytest.mark.asyncio
    async def test_collect_pod_data(self, data_collector, mock_pod, mock_v1_client):
        """Test collecting comprehensive pod data"""
        result = await data_collector.collect_pod_data(mock_pod, mock_v1_client)
        
        # Verify basic pod info
        assert result["pod_name"] == "test-pod"
        assert result["namespace"] == "default"
        assert result["node_name"] == "test-node"
        assert result["phase"] == "Pending"
        assert result["creation_timestamp"] == "2025-01-01T00:00:00Z"
        
        # Verify failure info
        assert result["failure_reason"] == "ImagePullBackOff"
        assert result["failure_message"] == "Failed to pull image"
        
        # Verify container statuses
        assert len(result["container_statuses"]) == 1
        container = result["container_statuses"][0]
        assert container["name"] == "test-container"
        assert container["ready"] == False
        assert container["image"] == "test:latest"
        assert container["reason"] == "ImagePullBackOff"
        
        # Verify events were collected
        assert len(result["events"]) == 1
        event = result["events"][0]
        assert event["type"] == "Warning"
        assert event["reason"] == "ImagePullBackOff"
        
        # Verify logs are empty (due to 403 error)
        assert result["logs"] == ""
        
        # Verify manifest was generated
        assert result["manifest"] is not None

    def test_get_failure_reason_from_container_status(self, data_collector):
        """Test extracting failure reason from container status"""
        # Create a pod with Running phase so it falls through to check container statuses
        pod = Mock()
        pod.status.phase = "Running"  # Not Pending, so it checks container statuses
        pod.status.container_statuses = [Mock()]

        container_status = pod.status.container_statuses[0]
        container_status.state.waiting = Mock()
        container_status.state.waiting.reason = "ImagePullBackOff"

        result = data_collector._get_failure_reason(pod)
        assert result == "ImagePullBackOff"

    def test_get_failure_reason_pending_phase(self, data_collector):
        """Test failure reason for pending phase"""
        pod = Mock()
        pod.status.phase = "Pending"
        pod.status.container_statuses = None
        
        result = data_collector._get_failure_reason(pod)
        assert result == "Pending"

    def test_get_failure_message_from_container(self, data_collector, mock_pod):
        """Test extracting failure message from container status"""
        result = data_collector._get_failure_message(mock_pod)
        assert result == "Failed to pull image"

    def test_get_failure_message_from_events(self, data_collector):
        """Test extracting failure message from events when container message unavailable"""
        pod = Mock()
        pod.status.container_statuses = None
        
        events = [
            {
                "type": "Warning",
                "reason": "FailedMount",
                "message": "MountVolume.SetUp failed: secret 'test' not found"
            }
        ]
        
        result = data_collector._get_failure_message(pod, events)
        assert result == "MountVolume.SetUp failed: secret 'test' not found"

    def test_get_container_statuses_waiting_state(self, data_collector, mock_pod):
        """Test getting container statuses in waiting state"""
        result = data_collector._get_container_statuses(mock_pod)
        
        assert len(result) == 1
        container = result[0]
        assert container["name"] == "test-container"
        assert container["state"] == "waiting"
        assert container["reason"] == "ImagePullBackOff"
        assert container["message"] == "Failed to pull image"

    def test_get_container_statuses_terminated_state(self, data_collector):
        """Test getting container statuses in terminated state"""
        pod = Mock()
        pod.status.container_statuses = [Mock()]
        
        container_status = pod.status.container_statuses[0]
        container_status.name = "terminated-container"
        container_status.ready = False
        container_status.restart_count = 1
        container_status.image = "test:latest"
        container_status.state.waiting = None
        container_status.state.running = None
        container_status.state.terminated = Mock()
        container_status.state.terminated.exit_code = 1
        container_status.state.terminated.reason = "Error"
        
        result = data_collector._get_container_statuses(pod)

        assert len(result) == 1
        container = result[0]
        assert container["state"] == "terminated"
        assert container["exit_code"] == 1
        assert container["reason"] == "Error"


def _make_container_status(
    name="app",
    restart_count=0,
    waiting_reason=None,
    terminated_reason=None,
    terminated_exit_code=None,
    last_terminated_reason=None,
    last_terminated_exit_code=None,
):
    """Build a mock V1ContainerStatus with configurable waiting/terminated/last_state."""
    cs = Mock()
    cs.name = name
    cs.restart_count = restart_count

    cs.state = Mock()
    if waiting_reason is not None:
        cs.state.waiting = Mock()
        cs.state.waiting.reason = waiting_reason
        cs.state.waiting.message = None
    else:
        cs.state.waiting = None

    if terminated_reason is not None:
        cs.state.terminated = Mock()
        cs.state.terminated.reason = terminated_reason
        cs.state.terminated.exit_code = terminated_exit_code
    else:
        cs.state.terminated = None

    cs.state.running = None

    cs.last_state = Mock()
    if last_terminated_reason is not None:
        cs.last_state.terminated = Mock()
        cs.last_state.terminated.reason = last_terminated_reason
        cs.last_state.terminated.exit_code = last_terminated_exit_code
    else:
        cs.last_state.terminated = None

    return cs


def _make_pod_with_statuses(container_statuses=None, init_container_statuses=None):
    """Build a mock pod carrying specific container/init container statuses."""
    pod = Mock()
    pod.metadata.name = "test-pod"
    pod.metadata.namespace = "default"
    pod.metadata.creation_timestamp.isoformat.return_value = "2025-01-01T00:00:00Z"
    pod.spec.node_name = "test-node"
    pod.status.phase = "Running"
    pod.status.container_statuses = container_statuses
    pod.status.init_container_statuses = init_container_statuses
    return pod


class _FakeConfig:
    def __init__(self, enabled=True, max_lines=1000):
        self.failure_logs_enabled = enabled
        self.failure_logs_max_lines = max_lines


class TestIdentifyCrashContainers:
    def setup_method(self):
        self.dc = DataCollector(_FakeConfig())

    def test_identify_crash_containers_crashloop(self):
        pod = _make_pod_with_statuses(container_statuses=[
            _make_container_status(
                name="app",
                restart_count=3,
                waiting_reason="CrashLoopBackOff",
                last_terminated_reason="Error",
                last_terminated_exit_code=1,
            )
        ])

        result = self.dc._identify_crash_containers(pod)

        assert len(result) == 1
        entry = result[0]
        assert entry["name"] == "app"
        assert entry["reason"] == "CrashLoopBackOff"
        assert entry["restart_count"] == 3
        assert entry["has_previous"] is True
        assert entry["exit_code"] == 1

    def test_identify_crash_containers_oomkilled_last_state(self):
        pod = _make_pod_with_statuses(container_statuses=[
            _make_container_status(
                name="mem-hog",
                restart_count=2,
                waiting_reason="CrashLoopBackOff",
                last_terminated_reason="OOMKilled",
                last_terminated_exit_code=137,
            )
        ])

        result = self.dc._identify_crash_containers(pod)

        assert len(result) == 1
        entry = result[0]
        # CrashLoopBackOff takes precedence in ordering since waiting is checked first,
        # but the container is eligible either way. Accept either classification.
        assert entry["reason"] in ("CrashLoopBackOff", "OOMKilled")
        assert entry["has_previous"] is True

    def test_identify_crash_containers_oomkilled_terminated_only(self):
        pod = _make_pod_with_statuses(container_statuses=[
            _make_container_status(
                name="mem-hog",
                restart_count=0,
                terminated_reason="OOMKilled",
                terminated_exit_code=137,
            )
        ])

        result = self.dc._identify_crash_containers(pod)
        assert len(result) == 1
        entry = result[0]
        assert entry["reason"] == "OOMKilled"
        assert entry["exit_code"] == 137
        assert entry["has_previous"] is False

    def test_identify_crash_containers_imagepullbackoff_excluded(self):
        pod = _make_pod_with_statuses(container_statuses=[
            _make_container_status(
                name="app",
                restart_count=0,
                waiting_reason="ImagePullBackOff",
            )
        ])

        result = self.dc._identify_crash_containers(pod)
        assert result == []

    def test_identify_crash_containers_first_crash_no_previous(self):
        pod = _make_pod_with_statuses(container_statuses=[
            _make_container_status(
                name="app",
                restart_count=0,
                waiting_reason="CrashLoopBackOff",
            )
        ])

        result = self.dc._identify_crash_containers(pod)
        assert len(result) == 1
        assert result[0]["has_previous"] is False
        assert result[0]["restart_count"] == 0

    def test_identify_crash_containers_init_container_included(self):
        pod = _make_pod_with_statuses(
            container_statuses=None,
            init_container_statuses=[
                _make_container_status(
                    name="init-1",
                    restart_count=1,
                    waiting_reason="CrashLoopBackOff",
                )
            ],
        )

        result = self.dc._identify_crash_containers(pod)
        assert len(result) == 1
        assert result[0]["name"] == "init-1"
        assert result[0]["has_previous"] is True


class TestGetFailureLogs:
    def setup_method(self):
        self.dc = DataCollector(_FakeConfig())

    @pytest.mark.asyncio
    async def test_get_failure_logs_success(self):
        v1 = Mock()
        log_text = "line1\nline2\nline3\nline4\n"
        v1.read_namespaced_pod_log.return_value = log_text

        crash_containers = [{
            "name": "app",
            "reason": "CrashLoopBackOff",
            "exit_code": 1,
            "restart_count": 2,
            "has_previous": True,
        }]

        result = await self.dc._get_failure_logs(v1, "default", "test-pod", crash_containers, 1000)

        assert result is not None
        assert result["version"] == 1
        assert result["encoding"] == "gzip+base64"
        container_entry = result["containers"]["app"]
        assert container_entry["error"] is None
        assert container_entry["current"] is None
        prev = container_entry["previous"]
        assert prev is not None
        assert prev["truncated"] is False
        assert prev["lines"] == 4
        assert prev["original_size"] == len(log_text.encode("utf-8"))

        # Round-trip through gzip+base64 must match the original bytes.
        decoded = gzip.decompress(base64.b64decode(prev["data"]))
        assert decoded == log_text.encode("utf-8")

        # Verify API call was made with previous=True
        v1.read_namespaced_pod_log.assert_called_once()
        kwargs = v1.read_namespaced_pod_log.call_args.kwargs
        assert kwargs["previous"] is True
        assert kwargs["container"] == "app"

    @pytest.mark.asyncio
    async def test_get_failure_logs_truncation(self):
        # Build a payload larger than the raw cap.
        big_line = "x" * 1024 + "\n"
        total_lines = (MAX_RAW_BYTES // len(big_line)) + 50  # well over the cap
        big_text = big_line * total_lines
        assert len(big_text.encode("utf-8")) > MAX_RAW_BYTES

        v1 = Mock()
        v1.read_namespaced_pod_log.return_value = big_text

        crash_containers = [{
            "name": "app",
            "reason": "CrashLoopBackOff",
            "exit_code": 1,
            "restart_count": 1,
            "has_previous": True,
        }]

        result = await self.dc._get_failure_logs(v1, "default", "test-pod", crash_containers, 1000)

        prev = result["containers"]["app"]["previous"]
        assert prev is not None
        assert prev["truncated"] is True
        assert prev["original_size"] <= MAX_RAW_BYTES

        decoded = gzip.decompress(base64.b64decode(prev["data"]))
        assert len(decoded) <= MAX_RAW_BYTES

    @pytest.mark.asyncio
    async def test_get_failure_logs_no_previous_400(self):
        v1 = Mock()
        v1.read_namespaced_pod_log.side_effect = ApiException(status=400, reason="Bad Request")

        crash_containers = [{
            "name": "app", "reason": "CrashLoopBackOff",
            "exit_code": None, "restart_count": 1, "has_previous": True,
        }]

        result = await self.dc._get_failure_logs(v1, "default", "test-pod", crash_containers, 1000)
        entry = result["containers"]["app"]
        assert entry["previous"] is None
        assert entry["error"] == "no_previous_instance"

    @pytest.mark.asyncio
    async def test_get_failure_logs_permission_denied_403(self):
        v1 = Mock()
        v1.read_namespaced_pod_log.side_effect = ApiException(status=403, reason="Forbidden")

        crash_containers = [{
            "name": "app", "reason": "CrashLoopBackOff",
            "exit_code": None, "restart_count": 1, "has_previous": True,
        }]

        result = await self.dc._get_failure_logs(v1, "default", "test-pod", crash_containers, 1000)
        assert result["containers"]["app"]["error"] == "permission_denied"

    @pytest.mark.asyncio
    async def test_get_failure_logs_timeout(self):
        v1 = Mock()
        v1.read_namespaced_pod_log.side_effect = TimeoutError("timed out")

        crash_containers = [{
            "name": "app", "reason": "CrashLoopBackOff",
            "exit_code": None, "restart_count": 1, "has_previous": True,
        }]

        result = await self.dc._get_failure_logs(v1, "default", "test-pod", crash_containers, 1000)
        assert result["containers"]["app"]["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_get_failure_logs_empty_response(self):
        v1 = Mock()
        v1.read_namespaced_pod_log.return_value = ""

        crash_containers = [{
            "name": "app", "reason": "CrashLoopBackOff",
            "exit_code": None, "restart_count": 1, "has_previous": True,
        }]

        result = await self.dc._get_failure_logs(v1, "default", "test-pod", crash_containers, 1000)
        entry = result["containers"]["app"]
        assert entry["previous"] is None
        assert entry["error"] == "empty"

    @pytest.mark.asyncio
    async def test_get_failure_logs_no_previous_flag(self):
        """has_previous=False should not trigger the API call."""
        v1 = Mock()
        crash_containers = [{
            "name": "app", "reason": "CrashLoopBackOff",
            "exit_code": None, "restart_count": 0, "has_previous": False,
        }]

        result = await self.dc._get_failure_logs(v1, "default", "test-pod", crash_containers, 1000)

        assert result["containers"]["app"]["error"] == "no_previous_instance"
        assert result["containers"]["app"]["previous"] is None
        v1.read_namespaced_pod_log.assert_not_called()


class TestCollectPodDataFailureLogs:
    @pytest.fixture
    def v1_client_factory(self):
        def _build(events=None, pod_log="", previous_log=None, previous_exception=None):
            v1 = Mock()
            events_obj = Mock()
            events_obj.items = events or []
            v1.list_namespaced_event.return_value = events_obj

            def _read_log(*args, **kwargs):
                if kwargs.get("previous") is True:
                    if previous_exception is not None:
                        raise previous_exception
                    return previous_log if previous_log is not None else ""
                return pod_log

            v1.read_namespaced_pod_log.side_effect = _read_log
            return v1
        return _build

    @pytest.mark.asyncio
    async def test_collect_pod_data_disabled_no_api_call(self, v1_client_factory):
        dc = DataCollector(_FakeConfig(enabled=False))
        pod = _make_pod_with_statuses(container_statuses=[
            _make_container_status(
                name="app", restart_count=2,
                waiting_reason="CrashLoopBackOff",
            )
        ])
        v1 = v1_client_factory(pod_log="current\n", previous_log="prev\n")

        result = await dc.collect_pod_data(pod, v1)

        assert "failure_logs" not in result
        # Verify previous=True was NOT called; only the standard 50-line current fetch.
        for call in v1.read_namespaced_pod_log.call_args_list:
            assert call.kwargs.get("previous") is not True

    @pytest.mark.asyncio
    async def test_collect_pod_data_imagepullbackoff_skips_fetch(self, v1_client_factory):
        dc = DataCollector(_FakeConfig(enabled=True))
        pod = _make_pod_with_statuses(container_statuses=[
            _make_container_status(
                name="app", restart_count=0,
                waiting_reason="ImagePullBackOff",
            )
        ])
        v1 = v1_client_factory(pod_log="current\n", previous_log="should-not-be-read\n")

        result = await dc.collect_pod_data(pod, v1)

        assert "failure_logs" not in result
        for call in v1.read_namespaced_pod_log.call_args_list:
            assert call.kwargs.get("previous") is not True

    @pytest.mark.asyncio
    async def test_collect_pod_data_multi_container_only_oom_captured(self, v1_client_factory):
        dc = DataCollector(_FakeConfig(enabled=True))
        pod = _make_pod_with_statuses(container_statuses=[
            _make_container_status(
                name="healthy", restart_count=0,
            ),
            _make_container_status(
                name="oomer", restart_count=2,
                last_terminated_reason="OOMKilled",
                last_terminated_exit_code=137,
            ),
        ])
        v1 = v1_client_factory(pod_log="current\n", previous_log="oom-prev-logs\n")

        result = await dc.collect_pod_data(pod, v1)

        assert "failure_logs" in result
        containers = result["failure_logs"]["containers"]
        assert set(containers.keys()) == {"oomer"}
        prev = containers["oomer"]["previous"]
        assert prev is not None
        decoded = gzip.decompress(base64.b64decode(prev["data"]))
        assert decoded == b"oom-prev-logs\n"