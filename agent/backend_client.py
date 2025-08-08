import aiohttp
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self, backend_url: str):
        self.backend_url = backend_url.rstrip('/')

    async def report_failed_pod(self, pod_data: Dict[str, Any]):
        """Send failed pod data to backend"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.backend_url}/api/pods/failed",
                        json=pod_data,
                        headers={'Content-Type': 'application/json'}
                ) as response:
                    if response.status == 200:
                        logger.info(f"Successfully reported pod {pod_data['pod_name']}")
                    else:
                        logger.error(f"Backend returned status {response.status}")
        except Exception as e:
            logger.error(f"Failed to send data to backend: {e}")

    async def dismiss_deleted_pod(self, namespace: str, pod_name: str):
        """Notify backend that a pod was deleted"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.backend_url}/api/pods/dismiss-deleted",
                        json={"namespace": namespace, "pod_name": pod_name},
                        headers={'Content-Type': 'application/json'}
                ) as response:
                    if response.status == 200:
                        logger.info(f"Notified backend of deleted pod {namespace}/{pod_name}")
                    else:
                        logger.warning(f"Backend returned status {response.status} for dismiss")
        except Exception as e:
            logger.error(f"Failed to notify backend of deleted pod: {e}")
