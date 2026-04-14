import pytest
from unittest.mock import Mock, AsyncMock, patch

from services.security_scanner import SecurityScanner
from services.backend_client import BackendClient
from services.scanner_base import (
    ALLOWED_CAPABILITIES,
    DANGEROUS_CAPABILITIES,
    SYSTEM_NAMESPACES,
)


def _make_scanner():
    """Build a SecurityScanner with mocked clients and Kubernetes APIs.

    The composed helpers (exclusion_mgr, pod_scanner, resource_scanner,
    watch_mgr) are real instances pointing at this scanner, so tests
    exercise the real delegation paths.
    """
    with patch("services.security_scanner.BackendClient"), patch(
        "services.security_scanner.WebSocketClient"
    ):
        scanner = SecurityScanner()

    scanner.v1 = Mock()
    scanner.apps_v1 = Mock()
    scanner.rbac_v1 = Mock()
    scanner.networking_v1 = Mock()
    scanner.batch_v1 = Mock()
    scanner.policy_v1 = Mock()
    scanner.backend_client = AsyncMock()

    # Trusted-registries refresh hits the backend; no-op it and seed an
    # empty admin list so untrusted-registry checks behave deterministically.
    scanner.exclusion_mgr.refresh_trusted_registries = AsyncMock(return_value=True)
    scanner.exclusion_mgr.admin_trusted_registries = []

    return scanner


class TestSecurityScannerConstants:
    """Module-level security constants moved to services.scanner_base."""

    def test_dangerous_capabilities_defined(self):
        assert "SYS_ADMIN" in DANGEROUS_CAPABILITIES
        assert "NET_RAW" in DANGEROUS_CAPABILITIES
        assert "SYS_PTRACE" in DANGEROUS_CAPABILITIES
        assert len(DANGEROUS_CAPABILITIES) > 0

    def test_allowed_capabilities_defined(self):
        assert "NET_BIND_SERVICE" in ALLOWED_CAPABILITIES

    def test_system_namespaces_defined(self):
        assert "kube-system" in SYSTEM_NAMESPACES
        assert "kube-public" in SYSTEM_NAMESPACES
        assert "kube-node-lease" in SYSTEM_NAMESPACES


class TestSecurityScanner:
    @pytest.fixture
    def scanner(self):
        return _make_scanner()

    def test_is_namespace_excluded_system(self, scanner):
        """System namespaces are always excluded via ExclusionManager."""
        assert scanner.exclusion_mgr.is_namespace_excluded("kube-system") is True
        assert scanner.exclusion_mgr.is_namespace_excluded("kube-public") is True

    def test_is_namespace_excluded_custom(self, scanner):
        """Admin-configured excluded namespaces are honored."""
        scanner.exclusion_mgr.excluded_namespaces = ["my-excluded-ns"]
        assert scanner.exclusion_mgr.is_namespace_excluded("my-excluded-ns") is True
        assert scanner.exclusion_mgr.is_namespace_excluded("default") is False

    def test_is_namespace_excluded_default(self, scanner):
        assert scanner.exclusion_mgr.is_namespace_excluded("default") is False

    @pytest.mark.asyncio
    async def test_report_finding(self, scanner):
        """report_finding forwards to backend and tracks the resource."""
        finding = {
            "resource_type": "Pod",
            "resource_name": "test-pod",
            "namespace": "default",
            "severity": "high",
            "category": "Security",
            "title": "Test finding",
            "description": "Test description",
            "remediation": "Test remediation",
            "timestamp": "2025-01-01T00:00:00Z",
        }

        await scanner.report_finding(finding)

        scanner.backend_client.report_security_finding.assert_called_once_with(finding)
        assert ("Pod", "default", "test-pod") in scanner.tracked_resources

    @pytest.mark.asyncio
    async def test_handle_resource_deletion(self, scanner):
        """Deletion handling moved to WatchManager.handle_resource_deletion."""
        scanner.tracked_resources.add(("Pod", "default", "test-pod"))

        await scanner.watch_mgr.handle_resource_deletion("Pod", "default", "test-pod")

        scanner.backend_client.delete_findings_by_resource.assert_called_once_with(
            "Pod", "default", "test-pod"
        )
        assert ("Pod", "default", "test-pod") not in scanner.tracked_resources

    @pytest.mark.asyncio
    async def test_refresh_excluded_namespaces(self, scanner):
        """Refreshing excluded namespaces caches values on ExclusionManager."""
        scanner.backend_client.get_excluded_namespaces = AsyncMock(
            return_value=["excluded-ns-1", "excluded-ns-2"]
        )

        result = await scanner.exclusion_mgr.refresh_excluded_namespaces(force=True)

        assert result is True
        assert "excluded-ns-1" in scanner.exclusion_mgr.excluded_namespaces
        assert "excluded-ns-2" in scanner.exclusion_mgr.excluded_namespaces

    @pytest.mark.asyncio
    async def test_refresh_excluded_namespaces_failure(self, scanner):
        """On backend failure, refresh returns False and does not raise."""
        scanner.backend_client.get_excluded_namespaces = AsyncMock(
            side_effect=Exception("Connection error")
        )

        result = await scanner.exclusion_mgr.refresh_excluded_namespaces(force=True)

        assert result is False


class TestPodSecurityChecks:
    @pytest.fixture
    def scanner(self):
        return _make_scanner()

    def _create_mock_pod(self, name="test-pod", namespace="default", **kwargs):
        pod = Mock()
        pod.metadata.name = name
        pod.metadata.namespace = namespace
        # Avoid Mock() truthiness in `labels.get(...)` / `annotations or {}`.
        pod.metadata.labels = kwargs.get("labels", None)
        pod.metadata.annotations = kwargs.get("annotations", None)
        pod.spec.host_network = kwargs.get("host_network", False)
        pod.spec.host_pid = kwargs.get("host_pid", False)
        pod.spec.host_ipc = kwargs.get("host_ipc", False)
        pod.spec.volumes = kwargs.get("volumes", None)
        pod.spec.security_context = kwargs.get("pod_security_context", None)
        pod.spec.containers = kwargs.get("containers", [])
        pod.spec.init_containers = kwargs.get("init_containers", [])
        pod.spec.service_account_name = kwargs.get("service_account", "default")
        return pod

    def _create_mock_container(self, name="container", **kwargs):
        container = Mock()
        container.name = name
        container.security_context = kwargs.get("security_context", None)
        container.resources = kwargs.get("resources", None)
        container.ports = kwargs.get("ports", None)
        container.env = kwargs.get("env", None)
        # A real string image avoids Mock-arithmetic blowups in the
        # :latest / registry / pull-policy checks downstream.
        container.image = kwargs.get("image", "docker.io/library/nginx:1.25.0")
        container.image_pull_policy = kwargs.get("image_pull_policy", "IfNotPresent")
        return container

    @pytest.mark.asyncio
    async def test_scan_pod_host_network(self, scanner):
        """Detect hostNetwork pod via PodScanner.scan_pods."""
        container = self._create_mock_container()
        pod = self._create_mock_pod(host_network=True, containers=[container])

        scanner.v1.list_pod_for_all_namespaces.return_value = Mock(items=[pod])

        await scanner.pod_scanner.scan_pods()

        calls = scanner.backend_client.report_security_finding.call_args_list
        assert len(calls) > 0
        titles = [call[0][0]["title"].lower() for call in calls]
        assert any("host network" in t for t in titles)

    @pytest.mark.asyncio
    async def test_scan_pod_host_pid(self, scanner):
        container = self._create_mock_container()
        pod = self._create_mock_pod(host_pid=True, containers=[container])

        scanner.v1.list_pod_for_all_namespaces.return_value = Mock(items=[pod])

        await scanner.pod_scanner.scan_pods()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]["title"].lower() for call in calls]
        assert any("host pid" in t for t in titles)

    @pytest.mark.asyncio
    async def test_scan_pod_privileged_container(self, scanner):
        sec_ctx = Mock()
        sec_ctx.privileged = True
        sec_ctx.allow_privilege_escalation = True
        sec_ctx.capabilities = None
        sec_ctx.run_as_non_root = None
        sec_ctx.run_as_user = None
        sec_ctx.read_only_root_filesystem = None
        sec_ctx.seccomp_profile = None
        sec_ctx.se_linux_options = None

        container = self._create_mock_container(security_context=sec_ctx)
        pod = self._create_mock_pod(containers=[container])

        scanner.v1.list_pod_for_all_namespaces.return_value = Mock(items=[pod])

        await scanner.pod_scanner.scan_pods()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]["title"].lower() for call in calls]
        assert any("privileged" in t for t in titles)

    @pytest.mark.asyncio
    async def test_scan_pod_skips_system_namespace(self, scanner):
        """System namespaces are filtered out before per-pod scanning."""
        container = self._create_mock_container()
        pod = self._create_mock_pod(
            namespace="kube-system",
            host_network=True,
            containers=[container],
        )

        scanner.v1.list_pod_for_all_namespaces.return_value = Mock(items=[pod])

        await scanner.pod_scanner.scan_pods()

        scanner.backend_client.report_security_finding.assert_not_called()


class TestRBACChecks:
    @pytest.fixture
    def scanner(self):
        return _make_scanner()

    def _create_mock_cluster_role(self, name, rules):
        role = Mock()
        role.metadata.name = name
        role.rules = rules
        return role

    def _create_mock_rule(self, resources=None, verbs=None, api_groups=None):
        rule = Mock()
        rule.resources = resources or []
        rule.verbs = verbs or []
        rule.api_groups = api_groups or []
        return rule

    @pytest.mark.asyncio
    async def test_scan_rbac_wildcard_resources(self, scanner):
        rule = self._create_mock_rule(resources=["*"], verbs=["get"])
        role = self._create_mock_cluster_role("test-role", [rule])

        scanner.rbac_v1.list_cluster_role.return_value = Mock(items=[role])
        scanner.rbac_v1.list_role_for_all_namespaces.return_value = Mock(items=[])

        await scanner.resource_scanner.scan_rbac()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]["title"].lower() for call in calls]
        assert any("wildcard" in t for t in titles)

    @pytest.mark.asyncio
    async def test_scan_rbac_secrets_access(self, scanner):
        rule = self._create_mock_rule(resources=["secrets"], verbs=["get", "list"])
        role = self._create_mock_cluster_role("test-role", [rule])

        scanner.rbac_v1.list_cluster_role.return_value = Mock(items=[role])
        scanner.rbac_v1.list_role_for_all_namespaces.return_value = Mock(items=[])

        await scanner.resource_scanner.scan_rbac()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]["title"].lower() for call in calls]
        assert any("secrets" in t for t in titles)

    @pytest.mark.asyncio
    async def test_scan_rbac_skips_system_roles(self, scanner):
        """ClusterRoles with a 'system:' prefix are skipped."""
        rule = self._create_mock_rule(resources=["*"], verbs=["*"])
        role = self._create_mock_cluster_role("system:test-role", [rule])

        scanner.rbac_v1.list_cluster_role.return_value = Mock(items=[role])
        scanner.rbac_v1.list_role_for_all_namespaces.return_value = Mock(items=[])

        await scanner.resource_scanner.scan_rbac()

        scanner.backend_client.report_security_finding.assert_not_called()


class TestNetworkPolicyChecks:
    @pytest.fixture
    def scanner(self):
        return _make_scanner()

    @pytest.mark.asyncio
    async def test_scan_missing_network_policy(self, scanner):
        """Namespace with pods but no NetworkPolicy is flagged."""
        ns = Mock()
        ns.metadata.name = "test-ns"
        ns.metadata.labels = {}

        pod = Mock()
        pod.metadata.name = "test-pod"

        scanner.v1.list_namespace.return_value = Mock(items=[ns])
        scanner.v1.list_namespaced_pod.return_value = Mock(items=[pod])
        scanner.networking_v1.list_network_policy_for_all_namespaces.return_value = (
            Mock(items=[])
        )

        await scanner.resource_scanner.scan_network_policies()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]["title"].lower() for call in calls]
        assert any("networkpolicy" in t for t in titles)


class TestServiceChecks:
    @pytest.fixture
    def scanner(self):
        return _make_scanner()

    @pytest.mark.asyncio
    async def test_scan_loadbalancer_service(self, scanner):
        service = Mock()
        service.metadata.name = "test-svc"
        service.metadata.namespace = "default"
        service.spec.type = "LoadBalancer"

        scanner.v1.list_service_for_all_namespaces.return_value = Mock(items=[service])

        await scanner.resource_scanner.scan_services()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]["title"].lower() for call in calls]
        assert any("loadbalancer" in t for t in titles)

    @pytest.mark.asyncio
    async def test_scan_nodeport_service(self, scanner):
        service = Mock()
        service.metadata.name = "test-svc"
        service.metadata.namespace = "default"
        service.spec.type = "NodePort"

        scanner.v1.list_service_for_all_namespaces.return_value = Mock(items=[service])

        await scanner.resource_scanner.scan_services()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]["title"].lower() for call in calls]
        assert any("nodeport" in t for t in titles)


class TestBackendClientAuth:
    """Verify that the BackendClient uses SERVICE_TOKEN via X-Service-Token header."""

    def test_service_token_header_present_when_env_set(self, monkeypatch):
        monkeypatch.setenv("SERVICE_TOKEN", "test-secret-token")
        client = BackendClient("http://backend.local")

        headers = client._headers("application/json")

        assert headers.get("X-Service-Token") == "test-secret-token"
        assert headers.get("Content-Type") == "application/json"
        # Must not send the old Authorization/Bearer header anymore
        assert "Authorization" not in headers

    def test_service_token_header_absent_when_env_missing(self, monkeypatch):
        monkeypatch.delenv("SERVICE_TOKEN", raising=False)
        client = BackendClient("http://backend.local")

        headers = client._headers()

        assert "X-Service-Token" not in headers
        assert "Authorization" not in headers

    def test_auth_api_key_env_is_ignored(self, monkeypatch):
        """Legacy AUTH_API_KEY must not leak into outbound headers."""
        monkeypatch.delenv("SERVICE_TOKEN", raising=False)
        monkeypatch.setenv("AUTH_API_KEY", "legacy-should-not-be-used")
        client = BackendClient("http://backend.local")

        headers = client._headers("application/json")

        assert "Authorization" not in headers
        assert "X-Service-Token" not in headers

    @pytest.mark.asyncio
    async def test_report_security_finding_sends_service_token(self, monkeypatch):
        """Integration-style test: POST to /api/security/findings carries X-Service-Token."""
        monkeypatch.setenv("SERVICE_TOKEN", "outbound-token")
        client = BackendClient("http://backend.local")

        captured = {}

        class _FakeResponse:
            status = 200

            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

            async def json(self_inner):
                return {}

            async def text(self_inner):
                return ""

        class _FakeSession:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

            def post(self_inner, url, json=None, headers=None, timeout=None):
                captured["url"] = url
                captured["headers"] = headers
                return _FakeResponse()

        with patch(
            "services.backend_client.aiohttp.ClientSession", return_value=_FakeSession()
        ):
            ok = await client.report_security_finding(
                {
                    "resource_type": "Pod",
                    "resource_name": "p",
                    "namespace": "default",
                }
            )

        assert ok is True
        assert captured["url"].endswith("/api/security/findings")
        assert captured["headers"].get("X-Service-Token") == "outbound-token"
        assert "Authorization" not in captured["headers"]
