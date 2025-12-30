import aiohttp
import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self, backend_url: str):
        self.backend_url = backend_url.rstrip('/')

    async def report_security_finding(self, finding_data: Dict[str, Any]):
        """Send security finding to backend"""
        finding_identifier = f"{finding_data.get('resource_type', 'unknown')}/{finding_data.get('namespace', 'unknown')}/{finding_data.get('resource_name', 'unknown')}"

        try:
            logger.info(f"Sending security finding for {finding_identifier} to backend")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.backend_url}/api/security/findings",
                        json=finding_data,
                        headers={'Content-Type': 'application/json'},
                        timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        logger.info(f"Successfully reported security finding for {finding_identifier}")
                        return True
                    else:
                        try:
                            error_data = await response.json()
                            error_msg = error_data.get('message', error_data.get('detail', 'Unknown error'))
                            logger.error(f"Backend returned HTTP {response.status} for {finding_identifier}: {error_msg}")
                        except Exception:
                            try:
                                error_text = await response.text()
                                logger.error(f"Backend returned HTTP {response.status} for {finding_identifier}: {error_text}")
                            except Exception:
                                logger.error(f"Backend returned HTTP {response.status} for {finding_identifier} (no response body)")

                        return False

        except asyncio.TimeoutError:
            logger.error(f"Timeout while reporting security finding for {finding_identifier} (30s)")
            return False
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error while reporting security finding for {finding_identifier}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while reporting security finding for {finding_identifier}: {e}")
            return False

    async def clear_security_findings(self):
        """Clear all security findings before starting a new scan"""
        try:
            logger.info("Clearing previous security findings from backend")

            async with aiohttp.ClientSession() as session:
                async with session.post(
                        f"{self.backend_url}/api/security/scan/clear",
                        headers={'Content-Type': 'application/json'},
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info("Successfully cleared previous security findings")
                        return True
                    else:
                        logger.warning(f"Backend returned HTTP {response.status} when clearing findings")
                        return False

        except Exception as e:
            logger.warning(f"Could not clear previous security findings: {e}")
            return False

    async def delete_findings_by_resource(self, resource_type: str, namespace: str, resource_name: str) -> bool:
        """Delete all findings for a specific resource (when resource is deleted from cluster)"""
        resource_identifier = f"{resource_type}/{namespace}/{resource_name}"

        try:
            logger.info(f"Deleting findings for deleted resource: {resource_identifier}")

            async with aiohttp.ClientSession() as session:
                async with session.delete(
                        f"{self.backend_url}/api/security/findings/resource/{resource_type}/{namespace}/{resource_name}",
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        count = data.get('count', 0)
                        logger.info(f"Successfully deleted {count} findings for {resource_identifier}")
                        return True
                    else:
                        logger.warning(f"Backend returned HTTP {response.status} when deleting findings for {resource_identifier}")
                        return False

        except Exception as e:
            logger.warning(f"Could not delete findings for {resource_identifier}: {e}")
            return False

    async def get_excluded_namespaces(self) -> list:
        """Get list of excluded namespaces from backend"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"{self.backend_url}/api/admin/excluded-namespaces",
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        namespaces = [item.get('namespace') for item in data if item.get('namespace')]
                        logger.debug(f"Fetched excluded namespaces: {namespaces}")
                        return namespaces
                    else:
                        logger.warning(f"Backend returned HTTP {response.status} for excluded namespaces")
                        return []

        except asyncio.TimeoutError:
            logger.warning("Timeout while fetching excluded namespaces (10s)")
            return []
        except aiohttp.ClientError as e:
            logger.warning(f"HTTP client error while fetching excluded namespaces: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error fetching excluded namespaces: {e}")
            return []

    async def get_namespaces_to_rescan(self) -> list:
        """Get namespaces that need to be rescanned (clears cache on backend)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                        f"{self.backend_url}/api/admin/namespaces-to-rescan",
                        timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        namespaces = await response.json()
                        if namespaces:
                            logger.info(f"Namespaces to rescan: {namespaces}")
                        return namespaces
                    else:
                        logger.warning(f"Backend returned HTTP {response.status} for namespaces to rescan")
                        return []

        except asyncio.TimeoutError:
            logger.warning("Timeout while fetching namespaces to rescan (10s)")
            return []
        except aiohttp.ClientError as e:
            logger.warning(f"HTTP client error while fetching namespaces to rescan: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error fetching namespaces to rescan: {e}")
            return []