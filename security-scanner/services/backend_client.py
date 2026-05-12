import aiohttp
import asyncio
import logging
import os
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class BackendError(Exception):
    """Raised when a backend request fails in a way the caller should see."""


class BackendClient:
    def __init__(self, backend_url: str):
        self.backend_url = backend_url.rstrip("/")
        self._service_token = os.environ.get("SERVICE_TOKEN")
        if not self._service_token:
            logger.error(
                "SERVICE_TOKEN environment variable is not set. "
                "Outbound requests to the backend will be rejected with 401 "
                "if the backend requires authentication."
            )
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()

    def _headers(self, content_type: str = None) -> dict:
        """Build request headers, including the service token for ingest auth."""
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        if self._service_token:
            headers["X-Service-Token"] = self._service_token
        return headers

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy-create and return a shared aiohttp.ClientSession.

        Default timeout of 30s matches the longest per-request timeout in this
        module; individual requests pass their own timeout override where needed.
        """
        if self._session is None or getattr(self._session, "closed", False):
            async with self._session_lock:
                if self._session is None or getattr(self._session, "closed", False):
                    self._session = aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=30)
                    )
        return self._session

    async def close(self):
        """Close the shared aiohttp session, if open."""
        if self._session is not None and not getattr(self._session, "closed", False):
            try:
                await self._session.close()
            except Exception as e:
                logger.warning(f"Error closing BackendClient session: {e}")
        self._session = None

    async def health_check(self) -> None:
        """Probe backend ``GET /health``. Raises BackendError on failure.

        Used by the scanner's startup wait loop so the actual cause of a
        not-ready backend (timeout, refused connection, non-200 status)
        is preserved instead of being swallowed by exclusion-refresh.
        """
        url = f"{self.backend_url}/health"
        try:
            session = await self._get_session()
            async with session.get(
                url,
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status != 200:
                    raise BackendError(f"Health check returned HTTP {response.status}")
        except BackendError:
            raise
        except asyncio.TimeoutError as e:
            raise BackendError(f"Health check timed out (5s) for {url}") from e
        except aiohttp.ClientError as e:
            raise BackendError(f"Health check client error for {url}: {e}") from e
        except Exception as e:
            raise BackendError(f"Health check failed for {url}: {e}") from e

    async def report_security_finding(self, finding_data: Dict[str, Any]):
        """Send security finding to backend"""
        finding_identifier = f"{finding_data.get('resource_type', 'unknown')}/{finding_data.get('namespace', 'unknown')}/{finding_data.get('resource_name', 'unknown')}"

        try:
            logger.info(f"Sending security finding for {finding_identifier} to backend")

            session = await self._get_session()
            async with session.post(
                f"{self.backend_url}/api/security/findings",
                json=finding_data,
                headers=self._headers("application/json"),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    logger.info(
                        f"Successfully reported security finding for {finding_identifier}"
                    )
                    return True
                else:
                    try:
                        error_data = await response.json()
                        error_msg = error_data.get(
                            "message", error_data.get("detail", "Unknown error")
                        )
                        logger.error(
                            f"Backend returned HTTP {response.status} for {finding_identifier}: {error_msg}"
                        )
                    except Exception:
                        try:
                            error_text = await response.text()
                            logger.error(
                                f"Backend returned HTTP {response.status} for {finding_identifier}: {error_text}"
                            )
                        except Exception:
                            logger.error(
                                f"Backend returned HTTP {response.status} for {finding_identifier} (no response body)"
                            )

                    return False

        except asyncio.TimeoutError:
            logger.error(
                f"Timeout while reporting security finding for {finding_identifier} (30s)"
            )
            return False
        except aiohttp.ClientError as e:
            logger.error(
                f"HTTP client error while reporting security finding for {finding_identifier}: {e}"
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error while reporting security finding for {finding_identifier}: {e}"
            )
            return False

    async def clear_security_findings(self):
        """Clear all security findings before starting a new scan"""
        try:
            logger.info("Clearing previous security findings from backend")

            session = await self._get_session()
            async with session.post(
                f"{self.backend_url}/api/security/scan/clear",
                headers=self._headers("application/json"),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    logger.info("Successfully cleared previous security findings")
                    return True
                else:
                    logger.warning(
                        f"Backend returned HTTP {response.status} when clearing findings"
                    )
                    return False

        except Exception as e:
            logger.warning(f"Could not clear previous security findings: {e}")
            return False

    async def delete_findings_by_resource(
        self, resource_type: str, namespace: str, resource_name: str
    ) -> bool:
        """Delete all findings for a specific resource (when resource is deleted from cluster)"""
        resource_identifier = f"{resource_type}/{namespace}/{resource_name}"

        try:
            logger.info(
                f"Deleting findings for deleted resource: {resource_identifier}"
            )

            session = await self._get_session()
            async with session.delete(
                f"{self.backend_url}/api/security/findings/resource/{resource_type}/{namespace}/{resource_name}",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    count = data.get("count", 0)
                    logger.info(
                        f"Successfully deleted {count} findings for {resource_identifier}"
                    )
                    return True
                else:
                    logger.warning(
                        f"Backend returned HTTP {response.status} when deleting findings for {resource_identifier}"
                    )
                    return False

        except Exception as e:
            logger.warning(f"Could not delete findings for {resource_identifier}: {e}")
            return False

    async def report_scan_duration(self, duration_seconds: float):
        """Report security scan duration to backend for Prometheus metrics"""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.backend_url}/api/metrics/security-scan-duration",
                json={"duration_seconds": duration_seconds},
                headers=self._headers("application/json"),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    logger.info(f"Reported scan duration: {duration_seconds:.1f}s")
                    return True
                else:
                    logger.warning(
                        f"Failed to report scan duration: HTTP {response.status}"
                    )
                    return False
        except Exception as e:
            logger.warning(f"Error reporting scan duration: {e}")
            return False

    async def report_rescan_status(self, status: str, reason: str = None):
        """Report security rescan status to backend (started/completed)"""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.backend_url}/api/security/rescan-status",
                json={"status": status, "reason": reason},
                headers=self._headers("application/json"),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    logger.info(f"Reported rescan status: {status}")
                    return True
                else:
                    logger.warning(
                        f"Failed to report rescan status: HTTP {response.status}"
                    )
                    return False
        except Exception as e:
            logger.warning(f"Error reporting rescan status: {e}")
            return False

    async def get_excluded_namespaces(self) -> list:
        """Get list of excluded namespaces from backend

        Returns:
            List of excluded namespace names

        Raises:
            Exception: If unable to fetch from backend
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.backend_url}/api/admin/excluded-namespaces",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    namespaces = [
                        item.get("namespace") for item in data if item.get("namespace")
                    ]
                    logger.debug(f"Fetched excluded namespaces: {namespaces}")
                    return namespaces
                else:
                    raise Exception(f"Backend returned HTTP {response.status}")

        except asyncio.TimeoutError:
            raise Exception("Timeout while fetching excluded namespaces (10s)")
        except aiohttp.ClientError as e:
            raise Exception(f"HTTP client error: {e}")
        except Exception as e:
            # Re-raise if it's already our exception
            if (
                "Backend returned" in str(e)
                or "Timeout" in str(e)
                or "HTTP client" in str(e)
            ):
                raise
            raise Exception(f"Error fetching excluded namespaces: {e}")

    async def get_excluded_rules(self) -> list:
        """Get list of excluded rules from backend

        Returns:
            List of dicts with 'rule_title' and 'namespace' (None for global)

        Raises:
            Exception: If unable to fetch from backend
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.backend_url}/api/admin/excluded-rules",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    rules = [
                        {
                            "rule_title": item.get("rule_title"),
                            "namespace": item.get("namespace"),
                        }
                        for item in data
                        if item.get("rule_title")
                    ]
                    logger.debug(f"Fetched excluded rules: {rules}")
                    return rules
                else:
                    raise Exception(f"Backend returned HTTP {response.status}")

        except asyncio.TimeoutError:
            raise Exception("Timeout while fetching excluded rules (10s)")
        except aiohttp.ClientError as e:
            raise Exception(f"HTTP client error: {e}")
        except Exception as e:
            if (
                "Backend returned" in str(e)
                or "Timeout" in str(e)
                or "HTTP client" in str(e)
            ):
                raise
            raise Exception(f"Error fetching excluded rules: {e}")

    async def get_trusted_registries(self) -> list:
        """Get list of admin-added trusted container registries from backend

        Returns:
            List of registry strings (e.g. ['my-registry.example.com'])

        Raises:
            Exception: If unable to fetch from backend
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.backend_url}/api/admin/trusted-registries",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    registries = [
                        item.get("registry") for item in data if item.get("registry")
                    ]
                    logger.debug(f"Fetched trusted registries: {registries}")
                    return registries
                else:
                    raise Exception(f"Backend returned HTTP {response.status}")

        except asyncio.TimeoutError:
            raise Exception("Timeout while fetching trusted registries (10s)")
        except aiohttp.ClientError as e:
            raise Exception(f"HTTP client error: {e}")
        except Exception as e:
            if (
                "Backend returned" in str(e)
                or "Timeout" in str(e)
                or "HTTP client" in str(e)
            ):
                raise
            raise Exception(f"Error fetching trusted registries: {e}")
