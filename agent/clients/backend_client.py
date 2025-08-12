import aiohttp
import asyncio
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self, backend_url: str):
        self.backend_url = backend_url.rstrip('/')

    async def report_failed_pod(self, pod_data: Dict[str, Any]):
        """Send failed pod data to backend"""
        pod_identifier = f"{pod_data.get('namespace', 'unknown')}/{pod_data.get('pod_name', 'unknown')}"
        
        try:
            logger.info(f"Sending failure report for pod {pod_identifier} to backend")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.backend_url}/api/pods/failed",
                        json=pod_data,
                        headers={'Content-Type': 'application/json'},
                        timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Successfully reported pod {pod_identifier}")
                        return True
                    else:
                        # Try to get detailed error message from response
                        try:
                            error_data = await response.json()
                            error_msg = error_data.get('message', error_data.get('detail', 'Unknown error'))
                            error_type = error_data.get('error_type', 'Unknown')
                            error_id = error_data.get('error_id')
                            
                            logger.error(f"Backend returned HTTP {response.status} for pod {pod_identifier}")
                            logger.error(f"Error type: {error_type}")
                            logger.error(f"Error message: {error_msg}")
                            if error_id:
                                logger.error(f"Backend error ID: {error_id}")
                        except Exception:
                            # If we can't parse JSON, get text response
                            try:
                                error_text = await response.text()
                                logger.error(f"Backend returned HTTP {response.status} for pod {pod_identifier}: {error_text}")
                            except Exception:
                                logger.error(f"Backend returned HTTP {response.status} for pod {pod_identifier} (no response body)")
                        
                        return False
                        
        except asyncio.TimeoutError:
            logger.error(f"Timeout while reporting pod {pod_identifier} to backend (30s)")
            return False
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error while reporting pod {pod_identifier}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while reporting pod {pod_identifier} to backend: {e}")
            return False

    async def report_cluster_info(self, cluster_name: str):
        """Report cluster information to backend"""
        try:
            logger.info(f"Reporting cluster info to backend: {cluster_name}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.backend_url}/api/cluster/register",
                        json={"cluster_name": cluster_name},
                        headers={'Content-Type': 'application/json'},
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Successfully reported cluster info: {cluster_name}")
                        return True
                    else:
                        logger.warning(f"Backend returned HTTP {response.status} for cluster info")
                        return False
                        
        except Exception as e:
            logger.warning(f"Could not report cluster info to backend: {e}")
            return False

    async def dismiss_deleted_pod(self, namespace: str, pod_name: str):
        """Notify backend that a pod was deleted"""
        pod_identifier = f"{namespace}/{pod_name}"
        
        try:
            logger.info(f"Notifying backend that pod {pod_identifier} was deleted")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.backend_url}/api/pods/dismiss-deleted",
                        json={"namespace": namespace, "pod_name": pod_name},
                        headers={'Content-Type': 'application/json'},
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Successfully notified backend of deleted pod {pod_identifier}")
                        return True
                    else:
                        # Try to get detailed error message from response
                        try:
                            error_data = await response.json()
                            error_msg = error_data.get('message', error_data.get('detail', 'Unknown error'))
                            logger.warning(f"Backend returned HTTP {response.status} for dismiss of pod {pod_identifier}: {error_msg}")
                        except Exception:
                            logger.warning(f"Backend returned HTTP {response.status} for dismiss of pod {pod_identifier}")
                        return False
                        
        except asyncio.TimeoutError:
            logger.warning(f"Timeout while notifying backend of deleted pod {pod_identifier} (10s)")
            return False
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error while notifying backend of deleted pod {pod_identifier}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while notifying backend of deleted pod {pod_identifier}: {e}")
            return False
