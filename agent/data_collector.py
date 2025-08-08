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

        # Basic pod info
        pod_data = {
            'pod_name': pod_name,
            'namespace': namespace,
            'node_name': pod.spec.node_name,
            'phase': pod.status.phase,
            'creation_timestamp': pod.metadata.creation_timestamp.isoformat(),
            'failure_reason': self._get_failure_reason(pod),
            'failure_message': self._get_failure_message(pod),
            'container_statuses': self._get_container_statuses(pod),
            'events': await self._get_pod_events(v1_client, namespace, pod_name),
            'logs': await self._get_pod_logs(v1_client, namespace, pod_name),
            'manifest': self._get_pod_manifest(pod)
        }

        return pod_data

    def _get_failure_reason(self, pod) -> str:
        """Extract the primary failure reason"""
        if pod.status.phase == 'Pending':
            return 'Pending'

        if not pod.status.container_statuses:
            return 'Unknown'

        for container_status in pod.status.container_statuses:
            if container_status.state.waiting:
                return container_status.state.waiting.reason or 'Unknown'

        return 'Unknown'

    def _get_failure_message(self, pod) -> str:
        """Extract the failure message"""
        if not pod.status.container_statuses:
            return ''

        for container_status in pod.status.container_statuses:
            if container_status.state.waiting and container_status.state.waiting.message:
                return container_status.state.waiting.message

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

    def _get_pod_manifest(self, pod) -> str:
        """Get the pod manifest as YAML"""
        try:
            # Convert pod object to dict and then to YAML
            pod_dict = pod.to_dict()
            logger.info(f"Generating manifest for pod {pod.metadata.name}")
            
            # Clean up the manifest - remove runtime status info
            if 'status' in pod_dict:
                del pod_dict['status']
            
            # Remove some metadata fields that aren't useful for manifest viewing
            if 'metadata' in pod_dict:
                metadata = pod_dict['metadata']
                for field in ['resource_version', 'uid', 'creation_timestamp', 'managed_fields']:
                    if field in metadata:
                        del metadata[field]
            
            # Convert to YAML
            manifest = yaml.safe_dump(pod_dict, default_flow_style=False, sort_keys=False)
            logger.info(f"Generated manifest length: {len(manifest)} characters")
            return manifest
        except Exception as e:
            logger.error(f"Could not generate pod manifest: {e}")
            return "# Error generating pod manifest"
