import logging
import yaml
from typing import Dict, Any, Optional
from kubernetes import client
from datetime import datetime

logger = logging.getLogger(__name__)


class DataCollector:
    def __init__(self):
        pass

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

        return pod_data

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
