import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from services.security_scanner import SecurityScanner


class TestSecurityScanner:

    @pytest.fixture
    def scanner(self):
        """Create SecurityScanner instance with mocked clients"""
        with patch('services.security_scanner.BackendClient'), \
             patch('services.security_scanner.WebSocketClient'):
            scanner = SecurityScanner()
            scanner.v1 = Mock()
            scanner.apps_v1 = Mock()
            scanner.rbac_v1 = Mock()
            scanner.networking_v1 = Mock()
            scanner.batch_v1 = Mock()
            scanner.policy_v1 = Mock()
            scanner.backend_client = AsyncMock()
            return scanner

    def test_dangerous_capabilities_defined(self, scanner):
        """Test that dangerous capabilities list is properly defined"""
        assert 'SYS_ADMIN' in scanner.DANGEROUS_CAPABILITIES
        assert 'NET_RAW' in scanner.DANGEROUS_CAPABILITIES
        assert 'SYS_PTRACE' in scanner.DANGEROUS_CAPABILITIES
        assert len(scanner.DANGEROUS_CAPABILITIES) > 0

    def test_allowed_capabilities_defined(self, scanner):
        """Test that allowed capabilities list is properly defined"""
        assert 'NET_BIND_SERVICE' in scanner.ALLOWED_CAPABILITIES

    def test_system_namespaces_defined(self, scanner):
        """Test that system namespaces are properly defined"""
        assert 'kube-system' in scanner.SYSTEM_NAMESPACES
        assert 'kube-public' in scanner.SYSTEM_NAMESPACES
        assert 'kube-node-lease' in scanner.SYSTEM_NAMESPACES

    def test_is_namespace_excluded_system(self, scanner):
        """Test that system namespaces are excluded"""
        assert scanner._is_namespace_excluded('kube-system') == True
        assert scanner._is_namespace_excluded('kube-public') == True

    def test_is_namespace_excluded_custom(self, scanner):
        """Test custom namespace exclusion"""
        scanner.excluded_namespaces = ['my-excluded-ns']
        assert scanner._is_namespace_excluded('my-excluded-ns') == True
        assert scanner._is_namespace_excluded('default') == False

    def test_is_namespace_excluded_default(self, scanner):
        """Test that default namespace is not excluded"""
        assert scanner._is_namespace_excluded('default') == False

    @pytest.mark.asyncio
    async def test_report_finding(self, scanner):
        """Test reporting a finding to backend"""
        finding = {
            "resource_type": "Pod",
            "resource_name": "test-pod",
            "namespace": "default",
            "severity": "high",
            "category": "Security",
            "title": "Test finding",
            "description": "Test description",
            "remediation": "Test remediation",
            "timestamp": "2025-01-01T00:00:00Z"
        }

        await scanner.report_finding(finding)

        scanner.backend_client.report_security_finding.assert_called_once_with(finding)
        assert ("Pod", "default", "test-pod") in scanner.tracked_resources

    @pytest.mark.asyncio
    async def test_handle_resource_deletion(self, scanner):
        """Test handling resource deletion"""
        # Add a tracked resource
        scanner.tracked_resources.add(("Pod", "default", "test-pod"))

        await scanner._handle_resource_deletion("Pod", "default", "test-pod")

        scanner.backend_client.delete_findings_by_resource.assert_called_once_with(
            "Pod", "default", "test-pod"
        )
        assert ("Pod", "default", "test-pod") not in scanner.tracked_resources

    @pytest.mark.asyncio
    async def test_refresh_excluded_namespaces(self, scanner):
        """Test refreshing excluded namespaces from backend"""
        scanner.backend_client.get_excluded_namespaces = AsyncMock(
            return_value=['excluded-ns-1', 'excluded-ns-2']
        )

        result = await scanner._refresh_excluded_namespaces(force=True)

        assert result == True
        assert 'excluded-ns-1' in scanner.excluded_namespaces
        assert 'excluded-ns-2' in scanner.excluded_namespaces

    @pytest.mark.asyncio
    async def test_refresh_excluded_namespaces_failure(self, scanner):
        """Test handling failure when refreshing excluded namespaces"""
        scanner.backend_client.get_excluded_namespaces = AsyncMock(
            side_effect=Exception("Connection error")
        )

        result = await scanner._refresh_excluded_namespaces(force=True)

        assert result == False


class TestPodSecurityChecks:

    @pytest.fixture
    def scanner(self):
        """Create SecurityScanner instance"""
        with patch('services.security_scanner.BackendClient'), \
             patch('services.security_scanner.WebSocketClient'):
            scanner = SecurityScanner()
            scanner.v1 = Mock()
            scanner.backend_client = AsyncMock()
            return scanner

    def _create_mock_pod(self, name="test-pod", namespace="default", **kwargs):
        """Helper to create a mock pod"""
        pod = Mock()
        pod.metadata.name = name
        pod.metadata.namespace = namespace
        pod.spec.host_network = kwargs.get('host_network', False)
        pod.spec.host_pid = kwargs.get('host_pid', False)
        pod.spec.host_ipc = kwargs.get('host_ipc', False)
        pod.spec.volumes = kwargs.get('volumes', None)
        pod.spec.security_context = kwargs.get('pod_security_context', None)
        pod.spec.containers = kwargs.get('containers', [])
        pod.spec.init_containers = kwargs.get('init_containers', [])
        pod.spec.service_account_name = kwargs.get('service_account', 'default')
        return pod

    def _create_mock_container(self, name="container", **kwargs):
        """Helper to create a mock container"""
        container = Mock()
        container.name = name
        container.security_context = kwargs.get('security_context', None)
        container.resources = kwargs.get('resources', None)
        container.ports = kwargs.get('ports', None)
        container.env = kwargs.get('env', None)
        return container

    @pytest.mark.asyncio
    async def test_scan_pod_host_network(self, scanner):
        """Test detection of hostNetwork pod"""
        container = self._create_mock_container()
        pod = self._create_mock_pod(host_network=True, containers=[container])

        scanner.v1.list_pod_for_all_namespaces.return_value = Mock(items=[pod])

        await scanner.scan_pods()

        # Check that a finding was reported
        calls = scanner.backend_client.report_security_finding.call_args_list
        assert len(calls) > 0
        finding = calls[0][0][0]
        assert 'host network' in finding['title'].lower()

    @pytest.mark.asyncio
    async def test_scan_pod_host_pid(self, scanner):
        """Test detection of hostPID pod"""
        container = self._create_mock_container()
        pod = self._create_mock_pod(host_pid=True, containers=[container])

        scanner.v1.list_pod_for_all_namespaces.return_value = Mock(items=[pod])

        await scanner.scan_pods()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]['title'].lower() for call in calls]
        assert any('host pid' in t for t in titles)

    @pytest.mark.asyncio
    async def test_scan_pod_privileged_container(self, scanner):
        """Test detection of privileged container"""
        sec_ctx = Mock()
        sec_ctx.privileged = True
        sec_ctx.allow_privilege_escalation = True
        sec_ctx.capabilities = None
        sec_ctx.run_as_non_root = None
        sec_ctx.run_as_user = None
        sec_ctx.read_only_root_filesystem = None

        container = self._create_mock_container(security_context=sec_ctx)
        pod = self._create_mock_pod(containers=[container])

        scanner.v1.list_pod_for_all_namespaces.return_value = Mock(items=[pod])

        await scanner.scan_pods()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]['title'].lower() for call in calls]
        assert any('privileged' in t for t in titles)

    @pytest.mark.asyncio
    async def test_scan_pod_skips_system_namespace(self, scanner):
        """Test that system namespaces are skipped"""
        container = self._create_mock_container()
        pod = self._create_mock_pod(
            namespace='kube-system',
            host_network=True,
            containers=[container]
        )

        scanner.v1.list_pod_for_all_namespaces.return_value = Mock(items=[pod])

        await scanner.scan_pods()

        # No findings should be reported for system namespace
        scanner.backend_client.report_security_finding.assert_not_called()


class TestRBACChecks:

    @pytest.fixture
    def scanner(self):
        """Create SecurityScanner instance"""
        with patch('services.security_scanner.BackendClient'), \
             patch('services.security_scanner.WebSocketClient'):
            scanner = SecurityScanner()
            scanner.rbac_v1 = Mock()
            scanner.backend_client = AsyncMock()
            return scanner

    def _create_mock_cluster_role(self, name, rules):
        """Helper to create a mock ClusterRole"""
        role = Mock()
        role.metadata.name = name
        role.rules = rules
        return role

    def _create_mock_rule(self, resources=None, verbs=None, api_groups=None):
        """Helper to create a mock RBAC rule"""
        rule = Mock()
        rule.resources = resources or []
        rule.verbs = verbs or []
        rule.api_groups = api_groups or []
        return rule

    @pytest.mark.asyncio
    async def test_scan_rbac_wildcard_resources(self, scanner):
        """Test detection of wildcard resource permissions"""
        rule = self._create_mock_rule(resources=['*'], verbs=['get'])
        role = self._create_mock_cluster_role('test-role', [rule])

        scanner.rbac_v1.list_cluster_role.return_value = Mock(items=[role])
        scanner.rbac_v1.list_role_for_all_namespaces.return_value = Mock(items=[])

        await scanner.scan_rbac()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]['title'].lower() for call in calls]
        assert any('wildcard' in t for t in titles)

    @pytest.mark.asyncio
    async def test_scan_rbac_secrets_access(self, scanner):
        """Test detection of secrets access permissions"""
        rule = self._create_mock_rule(resources=['secrets'], verbs=['get', 'list'])
        role = self._create_mock_cluster_role('test-role', [rule])

        scanner.rbac_v1.list_cluster_role.return_value = Mock(items=[role])
        scanner.rbac_v1.list_role_for_all_namespaces.return_value = Mock(items=[])

        await scanner.scan_rbac()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]['title'].lower() for call in calls]
        assert any('secrets' in t for t in titles)

    @pytest.mark.asyncio
    async def test_scan_rbac_skips_system_roles(self, scanner):
        """Test that system roles are skipped"""
        rule = self._create_mock_rule(resources=['*'], verbs=['*'])
        role = self._create_mock_cluster_role('system:test-role', [rule])

        scanner.rbac_v1.list_cluster_role.return_value = Mock(items=[role])
        scanner.rbac_v1.list_role_for_all_namespaces.return_value = Mock(items=[])

        await scanner.scan_rbac()

        # No findings for system: prefixed roles
        scanner.backend_client.report_security_finding.assert_not_called()


class TestNetworkPolicyChecks:

    @pytest.fixture
    def scanner(self):
        """Create SecurityScanner instance"""
        with patch('services.security_scanner.BackendClient'), \
             patch('services.security_scanner.WebSocketClient'):
            scanner = SecurityScanner()
            scanner.v1 = Mock()
            scanner.networking_v1 = Mock()
            scanner.backend_client = AsyncMock()
            return scanner

    @pytest.mark.asyncio
    async def test_scan_missing_network_policy(self, scanner):
        """Test detection of namespace without NetworkPolicy"""
        # Create a namespace with pods but no network policy
        ns = Mock()
        ns.metadata.name = 'test-ns'
        ns.metadata.labels = {}

        pod = Mock()
        pod.metadata.name = 'test-pod'

        scanner.v1.list_namespace.return_value = Mock(items=[ns])
        scanner.v1.list_namespaced_pod.return_value = Mock(items=[pod])
        scanner.networking_v1.list_network_policy_for_all_namespaces.return_value = Mock(items=[])

        await scanner.scan_network_policies()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]['title'].lower() for call in calls]
        assert any('networkpolicy' in t for t in titles)


class TestServiceChecks:

    @pytest.fixture
    def scanner(self):
        """Create SecurityScanner instance"""
        with patch('services.security_scanner.BackendClient'), \
             patch('services.security_scanner.WebSocketClient'):
            scanner = SecurityScanner()
            scanner.v1 = Mock()
            scanner.backend_client = AsyncMock()
            return scanner

    @pytest.mark.asyncio
    async def test_scan_loadbalancer_service(self, scanner):
        """Test detection of LoadBalancer service"""
        service = Mock()
        service.metadata.name = 'test-svc'
        service.metadata.namespace = 'default'
        service.spec.type = 'LoadBalancer'

        scanner.v1.list_service_for_all_namespaces.return_value = Mock(items=[service])

        await scanner.scan_services()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]['title'].lower() for call in calls]
        assert any('loadbalancer' in t for t in titles)

    @pytest.mark.asyncio
    async def test_scan_nodeport_service(self, scanner):
        """Test detection of NodePort service"""
        service = Mock()
        service.metadata.name = 'test-svc'
        service.metadata.namespace = 'default'
        service.spec.type = 'NodePort'

        scanner.v1.list_service_for_all_namespaces.return_value = Mock(items=[service])

        await scanner.scan_services()

        calls = scanner.backend_client.report_security_finding.call_args_list
        titles = [call[0][0]['title'].lower() for call in calls]
        assert any('nodeport' in t for t in titles)
