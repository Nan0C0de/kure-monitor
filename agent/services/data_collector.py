import asyncio
import base64
import gzip
import logging
import yaml
from typing import Dict, Any, List, Optional
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)

# Safety cap on raw (pre-gzip) log bytes per container log block. Not tuneable.
MAX_RAW_BYTES = 256 * 1024  # 256 KB

# Per-request Kubernetes API timeout (seconds) for log fetches.
LOG_FETCH_TIMEOUT = 10

# Byte limit passed to Kubernetes API to avoid pulling huge logs server-side.
LOG_FETCH_LIMIT_BYTES = 262144  # 256 KB


class DataCollector:
    def __init__(self, config=None):
        # Config is optional so existing callers/tests that construct
        # DataCollector() without a config continue to work. When absent,
        # failure log capture is disabled.
        self.config = config

    async def collect_pod_data(self, pod, v1_client) -> Dict[str, Any]:
        """Collect comprehensive data about a failed pod"""

        pod_name = pod.metadata.name
        namespace = pod.metadata.namespace

        # Get events first as they may be needed for failure message
        events = await self._get_pod_events(v1_client, namespace, pod_name)

        # Basic pod info
        pod_data = {
            'pod_name': pod_name,
            'namespace': namespace,
            'node_name': pod.spec.node_name,
            'phase': pod.status.phase,
            'creation_timestamp': pod.metadata.creation_timestamp.isoformat(),
            'failure_reason': self._get_failure_reason(pod, events),
            'failure_message': self._get_failure_message(pod, events),
            'container_statuses': self._get_container_statuses(pod),
            'events': events,
            'logs': await self._get_pod_logs(v1_client, namespace, pod_name),
            'manifest': self._get_pod_manifest(pod)
        }

        # Optional: capture previous-instance logs for CrashLoopBackOff / OOMKilled only.
        # Best-effort; failures here must never break the report.
        if self.config is not None and getattr(self.config, 'failure_logs_enabled', False):
            try:
                crash_containers = self._identify_crash_containers(pod)
                if crash_containers:
                    max_lines = getattr(self.config, 'failure_logs_max_lines', 1000)
                    failure_logs = await self._get_failure_logs(
                        v1_client, namespace, pod_name, crash_containers, max_lines
                    )
                    if failure_logs is not None:
                        pod_data['failure_logs'] = failure_logs
            except Exception as e:
                # Outer safety net - never let failure log capture break collection.
                logger.warning(
                    f"Unexpected error during failure log capture for {namespace}/{pod_name}: "
                    f"{e.__class__.__name__}: {e}"
                )

        return pod_data

    def _identify_crash_containers(self, pod) -> List[Dict[str, Any]]:
        """Identify containers eligible for failure log capture.

        Eligibility rules (checked for both regular and init containers):
          - CrashLoopBackOff: state.waiting.reason == "CrashLoopBackOff"
          - OOMKilled: state.terminated.reason == "OOMKilled" OR
                       last_state.terminated.reason == "OOMKilled"

        All other failure reasons (ImagePullBackOff, Pending, etc.) are skipped.
        """
        results: List[Dict[str, Any]] = []

        all_statuses = []
        if getattr(pod.status, 'init_container_statuses', None):
            all_statuses.extend(pod.status.init_container_statuses)
        if getattr(pod.status, 'container_statuses', None):
            all_statuses.extend(pod.status.container_statuses)

        for cs in all_statuses:
            name = getattr(cs, 'name', None)
            restart_count = getattr(cs, 'restart_count', 0) or 0
            state = getattr(cs, 'state', None)
            last_state = getattr(cs, 'last_state', None)

            reason = None
            exit_code = None

            # CrashLoopBackOff check (waiting state)
            waiting = getattr(state, 'waiting', None) if state else None
            if waiting and getattr(waiting, 'reason', None) == 'CrashLoopBackOff':
                reason = 'CrashLoopBackOff'
                # Try to find exit code from last_state.terminated if available
                lt = getattr(last_state, 'terminated', None) if last_state else None
                if lt is not None:
                    exit_code = getattr(lt, 'exit_code', None)

            # OOMKilled check (current terminated)
            if reason is None:
                terminated = getattr(state, 'terminated', None) if state else None
                if terminated and getattr(terminated, 'reason', None) == 'OOMKilled':
                    reason = 'OOMKilled'
                    exit_code = getattr(terminated, 'exit_code', None)

            # OOMKilled check (last_state terminated)
            if reason is None:
                last_terminated = getattr(last_state, 'terminated', None) if last_state else None
                if last_terminated and getattr(last_terminated, 'reason', None) == 'OOMKilled':
                    reason = 'OOMKilled'
                    exit_code = getattr(last_terminated, 'exit_code', None)

            if reason is None:
                continue

            results.append({
                'name': name,
                'reason': reason,
                'exit_code': exit_code,
                'restart_count': restart_count,
                'has_previous': restart_count > 0,
            })

        return results

    async def _get_failure_logs(
        self,
        v1_client,
        namespace: str,
        pod_name: str,
        crash_containers: List[Dict[str, Any]],
        max_lines: int,
    ) -> Optional[Dict[str, Any]]:
        """Fetch gzip+base64 encoded logs for crashed containers.

        Best-effort: never raises. Returns None only on a completely
        unexpected outer failure (the caller omits the field).
        """
        try:
            containers_payload: Dict[str, Any] = {}
            permission_warning_logged = False

            for cc in crash_containers:
                cname = cc.get('name')
                has_previous = cc.get('has_previous', False)

                entry: Dict[str, Any] = {
                    'previous': None,
                    'current': None,
                    'error': None,
                }

                if has_previous:
                    text, err = await self._fetch_container_log(
                        v1_client, namespace, pod_name, cname,
                        previous=True, tail_lines=max_lines,
                    )
                    if err == 'permission_denied' and not permission_warning_logged:
                        logger.warning(
                            f"Permission denied fetching previous logs for "
                            f"{namespace}/{pod_name} (container={cname}); "
                            f"agent may be missing pods/log RBAC"
                        )
                        permission_warning_logged = True

                    if text is not None:
                        entry['previous'] = self._encode_log_block(text)
                    else:
                        entry['error'] = err
                else:
                    # No previous instance available (first crash).
                    entry['error'] = 'no_previous_instance'

                containers_payload[cname] = entry

            return {
                'version': 1,
                'encoding': 'gzip+base64',
                'containers': containers_payload,
            }
        except Exception as e:
            logger.warning(
                f"Unexpected outer failure in _get_failure_logs for "
                f"{namespace}/{pod_name}: {e.__class__.__name__}: {e}"
            )
            return None

    async def _fetch_container_log(
        self,
        v1_client,
        namespace: str,
        pod_name: str,
        container_name: str,
        previous: bool,
        tail_lines: int,
    ):
        """Fetch a single container log block.

        Returns (text_or_None, error_or_None). Never raises.
        """
        def _do_fetch():
            return v1_client.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container_name,
                previous=previous,
                tail_lines=tail_lines,
                limit_bytes=LOG_FETCH_LIMIT_BYTES,
                _request_timeout=LOG_FETCH_TIMEOUT,
            )

        try:
            loop = asyncio.get_running_loop()
            text = await loop.run_in_executor(None, _do_fetch)
        except ApiException as e:
            status = getattr(e, 'status', None)
            if status == 400:
                return None, 'no_previous_instance'
            if status == 403:
                return None, 'permission_denied'
            if status == 404:
                return None, 'container_not_found'
            logger.warning(
                f"API error fetching logs for {namespace}/{pod_name} "
                f"(container={container_name}, previous={previous}): "
                f"status={status} {e.__class__.__name__}"
            )
            return None, 'fetch_failed'
        except asyncio.TimeoutError:
            return None, 'timeout'
        except TimeoutError:
            return None, 'timeout'
        except Exception as e:
            logger.warning(
                f"Error fetching logs for {namespace}/{pod_name} "
                f"(container={container_name}, previous={previous}): "
                f"{e.__class__.__name__}: {e}"
            )
            return None, 'fetch_failed'

        if text is None or text == '':
            return None, 'empty'

        return text, None

    def _encode_log_block(self, text: str) -> Dict[str, Any]:
        """Encode a log block: enforce raw cap, gzip, base64.

        Returns dict with keys: data, original_size, lines, truncated.
        """
        raw_bytes = text.encode('utf-8')
        truncated = False
        if len(raw_bytes) > MAX_RAW_BYTES:
            raw_bytes = raw_bytes[-MAX_RAW_BYTES:]
            # Drop a possibly-broken leading partial line for cleanliness.
            nl = raw_bytes.find(b'\n')
            if 0 <= nl < len(raw_bytes) - 1:
                raw_bytes = raw_bytes[nl + 1:]
            truncated = True

        original_size = len(raw_bytes)
        # Count lines on the (possibly trimmed) raw bytes.
        lines = raw_bytes.count(b'\n')
        if original_size > 0 and not raw_bytes.endswith(b'\n'):
            lines += 1

        compressed = gzip.compress(raw_bytes, compresslevel=6)
        data = base64.b64encode(compressed).decode('ascii')

        return {
            'data': data,
            'original_size': original_size,
            'lines': lines,
            'truncated': truncated,
        }

    def _get_failure_reason(self, pod, events=None) -> str:
        """Extract the primary failure reason"""
        if pod.status.phase == 'Pending':
            # Check events for more specific pending reasons
            if events:
                for event in events:
                    if event.get('type') == 'Warning' and event.get('reason'):
                        reason = event.get('reason')
                        if reason in ['FailedMount', 'FailedScheduling', 'Failed', 'InvalidImageName', 'ErrImagePull', 'ImagePullBackOff',
                                     'CreateContainerError', 'RunContainerError', 'ErrImageNeverPull']:
                            return reason
            return 'Pending'

        if not pod.status.container_statuses:
            return 'Unknown'

        for container_status in pod.status.container_statuses:
            if container_status.state.waiting:
                return container_status.state.waiting.reason or 'Unknown'

        return 'Unknown'

    def _get_failure_message(self, pod, events=None) -> str:
        """Extract the failure message from containers or events"""
        # First try to get message from container statuses
        if pod.status.container_statuses:
            for container_status in pod.status.container_statuses:
                if container_status.state.waiting and container_status.state.waiting.message:
                    return container_status.state.waiting.message

        # If no container message, check pod events for failure details
        if events:
            for event in events:
                if event.get('type') == 'Warning' and event.get('message'):
                    # Prioritize mount and scheduling failures
                    reason = event.get('reason', '')
                    if reason in ['FailedMount', 'FailedScheduling', 'Failed']:
                        return event.get('message', '')

            # If no specific failure events, get the most recent warning message
            for event in reversed(events):  # Most recent first
                if event.get('type') == 'Warning' and event.get('message'):
                    return event.get('message', '')

        return ''

    def _get_container_statuses(self, pod) -> list:
        """Get container status information"""
        statuses = []

        if pod.status.container_statuses:
            for status in pod.status.container_statuses:
                container_info = {
                    'name': status.name,
                    'ready': status.ready,
                    'restart_count': status.restart_count,
                    'image': status.image
                }

                if status.state.waiting:
                    container_info['state'] = 'waiting'
                    container_info['reason'] = status.state.waiting.reason
                    container_info['message'] = status.state.waiting.message
                elif status.state.running:
                    container_info['state'] = 'running'
                elif status.state.terminated:
                    container_info['state'] = 'terminated'
                    container_info['exit_code'] = status.state.terminated.exit_code
                    container_info['reason'] = status.state.terminated.reason

                statuses.append(container_info)

        return statuses

    async def _get_pod_events(self, v1_client, namespace: str, pod_name: str) -> list:
        """Get recent events for the pod"""
        try:
            events = v1_client.list_namespaced_event(
                namespace=namespace,
                field_selector=f'involvedObject.name={pod_name}'
            )

            event_list = []
            for event in events.items[-5:]:  # Get last 5 events
                event_list.append({
                    'type': event.type,
                    'reason': event.reason,
                    'message': event.message,
                    'timestamp': event.first_timestamp.isoformat() if event.first_timestamp else None
                })

            return event_list
        except Exception as e:
            logger.warning(f"Could not get events for pod {pod_name}: {e}")
            return []

    async def _get_pod_logs(self, v1_client, namespace: str, pod_name: str) -> str:
        """Get recent logs from the pod"""
        try:
            logs = v1_client.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                tail_lines=50
            )
            return logs
        except Exception as e:
            logger.warning(f"Could not get logs for pod {pod_name}: {e}")
            return ''

    def _clean_dict(self, obj):
        """Recursively remove None/null values and empty objects from a dictionary"""
        if isinstance(obj, dict):
            cleaned = {}
            for key, value in obj.items():
                # Skip None values and empty lists/dicts
                if value is None or (isinstance(value, (list, dict)) and len(value) == 0):
                    continue
                # Convert snake_case to camelCase for Kubernetes convention
                if key in ['api_version', 'dns_policy', 'restart_policy', 'service_account_name',
                          'termination_grace_period_seconds', 'image_pull_policy', 'container_port',
                          'mount_path', 'read_only', 'host_port', 'host_ip']:
                    camel_key = self._to_camel_case(key)
                    cleaned[camel_key] = self._clean_dict(value)
                else:
                    cleaned[key] = self._clean_dict(value)
            return cleaned
        elif isinstance(obj, list):
            return [self._clean_dict(item) for item in obj if item is not None]
        else:
            return obj

    def _to_camel_case(self, snake_str):
        """Convert snake_case to camelCase"""
        components = snake_str.split('_')
        return components[0] + ''.join(word.capitalize() for word in components[1:])

    def _get_pod_manifest(self, pod) -> str:
        """Get the pod manifest as complete YAML (like kubectl get pod -o yaml)"""
        try:
            # Convert pod object to dict
            pod_dict = pod.to_dict()
            logger.info(f"Generating manifest for pod {pod.metadata.name}")

            # Keep status - it's important for debugging
            # Just ensure apiVersion and kind are present
            pod_dict['apiVersion'] = 'v1'
            pod_dict['kind'] = 'Pod'

            # Only remove truly useless runtime metadata fields
            if 'metadata' in pod_dict:
                metadata = pod_dict['metadata']
                # Only remove managed_fields as it's very verbose and not useful
                if 'managed_fields' in metadata:
                    del metadata['managed_fields']

            # Clean up the dictionary by removing None values
            clean_pod_dict = self._clean_dict(pod_dict)

            # Convert to clean YAML
            manifest = yaml.safe_dump(clean_pod_dict, default_flow_style=False, sort_keys=False)
            logger.info(f"Generated complete manifest length: {len(manifest)} characters")
            return manifest
        except Exception as e:
            logger.error(f"Could not generate pod manifest: {e}")
            return "# Error generating pod manifest"
