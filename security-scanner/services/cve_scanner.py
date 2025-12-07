import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Any

import aiohttp
from kubernetes import client, config

from services.backend_client import BackendClient

logger = logging.getLogger(__name__)

# Kubernetes official CVE feed URL
K8S_CVE_FEED_URL = "https://kubernetes.io/docs/reference/issues-security/official-cve-feed/index.json"


class CVEScanner:
    """
    Scans for Kubernetes CVEs from the official feed and compares against cluster version.

    This scanner fetches the official Kubernetes CVE feed and identifies which CVEs
    may affect your cluster based on the Kubernetes version.
    """

    def __init__(self):
        self.backend_url = os.getenv("BACKEND_URL", "http://kure-monitor-backend:8000")
        self.scan_interval = int(os.getenv("CVE_SCAN_INTERVAL", "86400"))  # Default: 24 hours
        self.backend_client = BackendClient(self.backend_url)
        self.v1 = None
        self.cluster_version: Optional[str] = None
        self.cluster_version_info: Optional[Dict] = None

    def _init_kubernetes_client(self):
        """Initialize Kubernetes client"""
        try:
            config.load_incluster_config()
            logger.info("Using in-cluster Kubernetes config")
        except config.ConfigException:
            try:
                config.load_kube_config()
                logger.info("Using local kubeconfig")
            except config.ConfigException:
                logger.error("Could not configure Kubernetes client")
                raise

        self.v1 = client.CoreV1Api()
        self.version_api = client.VersionApi()

    def _get_cluster_version(self) -> Optional[str]:
        """Get the Kubernetes cluster version"""
        try:
            version_info = self.version_api.get_code()
            self.cluster_version_info = {
                "major": version_info.major,
                "minor": version_info.minor.rstrip('+'),  # Remove trailing + if present
                "git_version": version_info.git_version,
            }
            # Extract semantic version (e.g., "1.28" from "v1.28.3")
            match = re.match(r'v?(\d+)\.(\d+)', version_info.git_version)
            if match:
                self.cluster_version = f"{match.group(1)}.{match.group(2)}"
                logger.info(f"Cluster version detected: {self.cluster_version} ({version_info.git_version})")
                return self.cluster_version
        except Exception as e:
            logger.error(f"Failed to get cluster version: {e}")
        return None

    async def fetch_cve_feed(self) -> Optional[Dict]:
        """Fetch the official Kubernetes CVE feed"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(K8S_CVE_FEED_URL, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Fetched CVE feed with {len(data.get('items', []))} entries")
                        return data
                    else:
                        logger.error(f"Failed to fetch CVE feed: HTTP {response.status}")
        except asyncio.TimeoutError:
            logger.error("Timeout fetching CVE feed")
        except Exception as e:
            logger.error(f"Error fetching CVE feed: {e}")
        return None

    def parse_affected_versions(self, content_text: str) -> Dict[str, Any]:
        """
        Parse CVE content to extract affected versions and other metadata.

        Returns a dict with:
        - affected_versions: list of version strings
        - fixed_versions: list of version strings
        - cvss_score: float or None
        - severity: string based on CVSS
        """
        result = {
            "affected_versions": [],
            "fixed_versions": [],
            "cvss_score": None,
            "severity": "medium",  # Default
            "components": [],
        }

        # Extract CVSS score
        cvss_match = re.search(r'CVSS[:\s]+(\d+\.?\d*)', content_text, re.IGNORECASE)
        if cvss_match:
            try:
                score = float(cvss_match.group(1))
                result["cvss_score"] = score
                # Map CVSS to severity
                if score >= 9.0:
                    result["severity"] = "critical"
                elif score >= 7.0:
                    result["severity"] = "high"
                elif score >= 4.0:
                    result["severity"] = "medium"
                else:
                    result["severity"] = "low"
            except ValueError:
                pass

        # Extract affected versions - look for patterns like "< 1.28.4" or "v1.27.x"
        # Common patterns in K8s CVE descriptions
        version_patterns = [
            r'(?:affected|vulnerable)[^.]*?(?:version[s]?)?[:\s]+([v\d\.\-\s,<>=]+)',
            r'(?:prior to|before|<)[:\s]*v?(\d+\.\d+\.\d+)',
            r'v?(\d+\.\d+\.\d+)\s*(?:and earlier|and below)',
            r'versions?\s+(\d+\.\d+)',
        ]

        for pattern in version_patterns:
            matches = re.findall(pattern, content_text, re.IGNORECASE)
            for match in matches:
                # Clean and add version
                versions = re.findall(r'(\d+\.\d+(?:\.\d+)?)', match)
                result["affected_versions"].extend(versions)

        # Extract fixed versions
        fixed_patterns = [
            r'(?:fixed|patched|resolved)[^.]*?(?:in|version[s]?)?[:\s]+v?(\d+\.\d+\.\d+)',
            r'upgrade to[:\s]+v?(\d+\.\d+\.\d+)',
        ]

        for pattern in fixed_patterns:
            matches = re.findall(pattern, content_text, re.IGNORECASE)
            result["fixed_versions"].extend(matches)

        # Extract affected components
        component_patterns = [
            r'(kubelet|kube-apiserver|kube-controller-manager|kube-scheduler|kubectl|etcd)',
            r'(ingress|cni|csi|container runtime)',
        ]

        for pattern in component_patterns:
            matches = re.findall(pattern, content_text, re.IGNORECASE)
            result["components"].extend([m.lower() for m in matches])

        # Deduplicate
        result["affected_versions"] = list(set(result["affected_versions"]))
        result["fixed_versions"] = list(set(result["fixed_versions"]))
        result["components"] = list(set(result["components"]))

        return result

    def is_version_affected(self, cve_data: Dict, cluster_version: str) -> bool:
        """
        Determine if the cluster version might be affected by a CVE.

        This is a best-effort check based on version parsing.
        Returns True if potentially affected (to err on side of caution).
        """
        try:
            cluster_parts = [int(x) for x in cluster_version.split('.')[:2]]
            cluster_major, cluster_minor = cluster_parts[0], cluster_parts[1]

            # Check against affected versions
            for affected in cve_data.get("affected_versions", []):
                affected_parts = [int(x) for x in affected.split('.')[:2]]
                if len(affected_parts) >= 2:
                    affected_major, affected_minor = affected_parts[0], affected_parts[1]
                    # If cluster version matches or is older than affected version
                    if (cluster_major, cluster_minor) <= (affected_major, affected_minor):
                        return True

            # Check against fixed versions - if cluster is older than fix, it's affected
            for fixed in cve_data.get("fixed_versions", []):
                fixed_parts = [int(x) for x in fixed.split('.')[:2]]
                if len(fixed_parts) >= 2:
                    fixed_major, fixed_minor = fixed_parts[0], fixed_parts[1]
                    if (cluster_major, cluster_minor) < (fixed_major, fixed_minor):
                        return True

            # If we couldn't determine, check if CVE is recent (within last 2 minor versions)
            # This is a fallback heuristic
            if not cve_data.get("affected_versions") and not cve_data.get("fixed_versions"):
                # Can't determine, assume potentially affected for recent CVEs
                return True

        except (ValueError, IndexError) as e:
            logger.warning(f"Could not parse version for CVE check: {e}")
            return True  # Err on side of caution

        return False

    async def scan_cves(self):
        """Main CVE scanning logic"""
        logger.info("Starting CVE scan...")

        # Get cluster version
        cluster_version = self._get_cluster_version()
        if not cluster_version:
            logger.warning("Could not determine cluster version, will report all CVEs")

        # Fetch CVE feed
        feed = await self.fetch_cve_feed()
        if not feed:
            logger.error("Failed to fetch CVE feed, skipping CVE scan")
            return

        items = feed.get("items", [])
        timestamp = datetime.utcnow().isoformat() + "Z"
        reported_count = 0

        for item in items:
            cve_id = item.get("id", "Unknown")
            summary = item.get("summary", "No summary available")
            content_text = item.get("content_text", "")
            date_published = item.get("date_published", "")
            url = item.get("url", "")
            external_url = item.get("external_url", "")

            # Parse CVE metadata
            cve_metadata = self.parse_affected_versions(content_text)

            # Check if this CVE affects our cluster
            is_affected = True
            if cluster_version:
                is_affected = self.is_version_affected(cve_metadata, cluster_version)

            if is_affected:
                # Build description
                description_parts = [summary]
                if cve_metadata["cvss_score"]:
                    description_parts.append(f"CVSS Score: {cve_metadata['cvss_score']}")
                if cve_metadata["components"]:
                    description_parts.append(f"Affected components: {', '.join(cve_metadata['components'])}")
                if cve_metadata["fixed_versions"]:
                    description_parts.append(f"Fixed in: {', '.join(cve_metadata['fixed_versions'])}")

                # Build remediation
                remediation_parts = []
                if cve_metadata["fixed_versions"]:
                    remediation_parts.append(f"Upgrade Kubernetes to version {cve_metadata['fixed_versions'][0]} or later.")
                else:
                    remediation_parts.append("Check the CVE details for specific remediation steps.")
                if external_url:
                    remediation_parts.append(f"CVE Details: {external_url}")
                if url:
                    remediation_parts.append(f"GitHub Issue: {url}")

                await self.report_cve({
                    "cve_id": cve_id,
                    "title": summary,
                    "description": " | ".join(description_parts),
                    "severity": cve_metadata["severity"],
                    "cvss_score": cve_metadata["cvss_score"],
                    "affected_versions": cve_metadata["affected_versions"],
                    "fixed_versions": cve_metadata["fixed_versions"],
                    "components": cve_metadata["components"],
                    "published_date": date_published,
                    "url": url,
                    "external_url": external_url,
                    "cluster_version": cluster_version or "unknown",
                    "timestamp": timestamp
                })
                reported_count += 1

        logger.info(f"CVE scan completed. Reported {reported_count} potentially affecting CVEs.")

    async def report_cve(self, cve_data: dict):
        """Report a CVE finding to the backend"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.backend_url}/api/security/cves",
                    json=cve_data,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        logger.debug(f"Reported CVE: {cve_data['cve_id']}")
                    else:
                        logger.warning(f"Failed to report CVE {cve_data['cve_id']}: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error reporting CVE {cve_data['cve_id']}: {e}")

    async def clear_cves(self):
        """Clear existing CVE records before new scan"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.backend_url}/api/security/cves/clear",
                    timeout=10
                ) as response:
                    if response.status == 200:
                        logger.info("Cleared existing CVE records")
                    else:
                        logger.warning(f"Failed to clear CVEs: HTTP {response.status}")
        except Exception as e:
            logger.error(f"Error clearing CVEs: {e}")

    async def start_scanning(self):
        """Start the CVE scanning loop"""
        logger.info(f"Starting CVE scanner (scan interval: {self.scan_interval}s)")
        logger.info(f"Backend URL: {self.backend_url}")

        self._init_kubernetes_client()

        while True:
            try:
                logger.info("Starting new CVE scan...")
                await self.clear_cves()
                await self.scan_cves()
                logger.info(f"CVE scan completed. Next scan in {self.scan_interval}s")
            except Exception as e:
                logger.error(f"Error during CVE scan: {e}")

            await asyncio.sleep(self.scan_interval)
