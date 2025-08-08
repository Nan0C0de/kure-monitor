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
        """Get the pod manifest as clean YAML"""
        try:
            # Convert pod object to dict
            pod_dict = pod.to_dict()
            logger.info(f"Generating manifest for pod {pod.metadata.name}")
            
            # Clean up the manifest - remove runtime status info
            if 'status' in pod_dict:
                del pod_dict['status']
            
            # Ensure apiVersion and kind are present
            pod_dict['apiVersion'] = 'v1'
            pod_dict['kind'] = 'Pod'
            
            # Remove runtime metadata fields that aren't useful for manifest viewing
            if 'metadata' in pod_dict:
                metadata = pod_dict['metadata']
                runtime_fields = ['resource_version', 'uid', 'self_link', 'generation', 
                                'managed_fields', 'owner_references', 'finalizers']
                for field in runtime_fields:
                    if field in metadata:
                        del metadata[field]
            
            # Remove spec fields that are runtime-generated
            if 'spec' in pod_dict:
                spec = pod_dict['spec']
                runtime_spec_fields = ['node_name', 'service_account', 'volumes', 'tolerations',
                                     'scheduler_name', 'priority', 'preemption_policy', 'enable_service_links']
                for field in runtime_spec_fields:
                    if field in spec:
                        del spec[field]
                
                # Clean container specs
                if 'containers' in spec:
                    for container in spec['containers']:
                        # Remove runtime container fields
                        runtime_container_fields = ['termination_message_path', 'termination_message_policy',
                                                  'volume_mounts', 'resources']
                        for field in runtime_container_fields:
                            if field in container:
                                del container[field]
            
            # Clean up the dictionary by removing None values
            clean_pod_dict = self._clean_dict(pod_dict)
            
            # Convert to clean YAML
            manifest = yaml.safe_dump(clean_pod_dict, default_flow_style=False, sort_keys=False)
            logger.info(f"Generated clean manifest length: {len(manifest)} characters")
            return manifest
        except Exception as e:
            logger.error(f"Could not generate pod manifest: {e}")
            return "# Error generating pod manifest"
