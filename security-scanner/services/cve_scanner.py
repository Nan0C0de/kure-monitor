import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Set

import aiohttp
from kubernetes import client, config

logger = logging.getLogger(__name__)

# NVD API endpoints
NVD_CVE_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_CPE_API_URL = "https://services.nvd.nist.gov/rest/json/cpes/2.0"


class CVEScanner:
    """
    Comprehensive CVE scanner that checks the entire Kubernetes cluster against NVD.

    Scans:
    - Kubernetes version and components
    - Container images running in pods
    - Node OS and kernel versions
    - Installed cluster components (etcd, CoreDNS, CNI, etc.)

    Uses NVD's API to dynamically look up CVEs - no hardcoded mappings needed.
    """

    def __init__(self):
        self.backend_url = os.getenv("BACKEND_URL", "http://kure-monitor-backend:8000")
        self.scan_interval = int(os.getenv("CVE_SCAN_INTERVAL", "3600"))  # Default: 1 hour
        self.nvd_api_key = os.getenv("NVD_API_KEY", "")  # Optional API key for higher rate limits
        self.v1 = None
        self.apps_v1 = None
        self.version_api = None
        self.cluster_version: Optional[str] = None
        self.cluster_version_full: Optional[str] = None

        # Cache for CPE lookups to avoid repeated API calls
        self.cpe_cache: Dict[str, Optional[str]] = {}

        # Rate limiting for NVD API (without key: 5 requests/30s, with key: 50 requests/30s)
        self.request_delay = 6.0 if not self.nvd_api_key else 0.6

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
        self.apps_v1 = client.AppsV1Api()
        self.version_api = client.VersionApi()

    def _get_cluster_info(self) -> Dict[str, Any]:
        """Get comprehensive cluster information"""
        info: Dict[str, Any] = {
            "kubernetes_version": None,
            "kubernetes_version_full": None,
            "platform": None,
            "nodes": [],
            "components": []
        }

        try:
            # Get Kubernetes version
            version_info = self.version_api.get_code()
            info["kubernetes_version_full"] = version_info.git_version
            self.cluster_version_full = version_info.git_version

            # Extract semantic version (e.g., "1.28.3" from "v1.28.3")
            match = re.match(r'v?(\d+\.\d+\.\d+)', version_info.git_version)
            if match:
                info["kubernetes_version"] = match.group(1)
                self.cluster_version = match.group(1)

            info["platform"] = version_info.platform
            logger.info(f"Cluster version: {info['kubernetes_version_full']} on {info['platform']}")

        except Exception as e:
            logger.error(f"Failed to get cluster version: {e}")

        try:
            # Get node information
            nodes = self.v1.list_node()
            for node in nodes.items:
                node_info = {
                    "name": node.metadata.name,
                    "os_image": node.status.node_info.os_image,
                    "kernel_version": node.status.node_info.kernel_version,
                    "container_runtime": node.status.node_info.container_runtime_version,
                    "kubelet_version": node.status.node_info.kubelet_version,
                    "kube_proxy_version": node.status.node_info.kube_proxy_version,
                }
                info["nodes"].append(node_info)
                logger.info(f"Node {node_info['name']}: {node_info['os_image']}, "
                           f"kernel {node_info['kernel_version']}, "
                           f"runtime {node_info['container_runtime']}")

        except Exception as e:
            logger.error(f"Failed to get node info: {e}")

        return info

    def _get_all_container_images(self) -> List[Dict[str, Any]]:
        """Get all unique container images running in the cluster"""
        images: Dict[str, Dict[str, Any]] = {}

        try:
            # Get all pods across all namespaces
            pods = self.v1.list_pod_for_all_namespaces()

            for pod in pods.items:
                namespace = pod.metadata.namespace
                pod_name = pod.metadata.name

                # Get images from containers
                if pod.spec.containers:
                    for container in pod.spec.containers:
                        image = container.image
                        if image and image not in images:
                            images[image] = {
                                "image": image,
                                "namespaces": set(),
                                "pods": []
                            }
                        if image and image in images:
                            images[image]["namespaces"].add(namespace)
                            images[image]["pods"].append(f"{namespace}/{pod_name}")

                # Get images from init containers
                if pod.spec.init_containers:
                    for container in pod.spec.init_containers:
                        image = container.image
                        if image and image not in images:
                            images[image] = {
                                "image": image,
                                "namespaces": set(),
                                "pods": []
                            }
                        if image and image in images:
                            images[image]["namespaces"].add(namespace)
                            images[image]["pods"].append(f"{namespace}/{pod_name}")

        except Exception as e:
            logger.error(f"Failed to get container images: {e}")

        # Convert sets to lists for JSON serialization
        for img in images.values():
            img["namespaces"] = list(img["namespaces"])

        logger.info(f"Found {len(images)} unique container images in cluster")
        return list(images.values())

    @staticmethod
    def _parse_image_name(image: str) -> Dict[str, Optional[str]]:
        """Parse container image name to extract product and version"""
        result: Dict[str, Optional[str]] = {
            "registry": None,
            "repository": None,
            "product": None,
            "tag": None,
            "version": None
        }

        # Remove registry prefix if present
        parts = image.split("/")
        if len(parts) >= 3:
            result["registry"] = parts[0]
            result["repository"] = "/".join(parts[1:-1])
            image_tag = parts[-1]
        elif len(parts) == 2:
            if "." in parts[0] or ":" in parts[0]:
                result["registry"] = parts[0]
                image_tag = parts[1]
            else:
                result["repository"] = parts[0]
                image_tag = parts[1]
        else:
            image_tag = parts[0]

        # Split image and tag
        if ":" in image_tag:
            name, tag = image_tag.rsplit(":", 1)
            # Handle digest format (sha256:...)
            if tag.startswith("sha256"):
                result["product"] = name
                result["tag"] = None
            else:
                result["product"] = name
                result["tag"] = tag
        else:
            result["product"] = image_tag
            result["tag"] = "latest"

        # Extract version from tag
        if result["tag"]:
            # Try to extract semantic version from tag
            version_match = re.search(r'(\d+\.\d+(?:\.\d+)?)', result["tag"])
            if version_match:
                result["version"] = version_match.group(1)

        return result

    async def _find_cpe_for_product(self, product_name: str) -> Optional[str]:
        """
        Dynamically search NVD's CPE dictionary for a product.
        Returns the CPE prefix if found, None otherwise.
        """
        # Check cache first
        if product_name in self.cpe_cache:
            return self.cpe_cache[product_name]

        params = {
            "keywordSearch": product_name,
            "resultsPerPage": 10
        }

        headers = {}
        if self.nvd_api_key:
            headers["apiKey"] = self.nvd_api_key

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    NVD_CPE_API_URL,
                    params=params,
                    headers=headers,
                    timeout=30
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        products = data.get("products", [])

                        if products:
                            # Find best match - prefer application CPEs
                            for prod in products:
                                cpe = prod.get("cpe", {})
                                cpe_name = cpe.get("cpeName", "")
                                # Check if product name is in the CPE
                                if product_name.lower() in cpe_name.lower():
                                    # Extract CPE prefix (without version)
                                    # Format: cpe:2.3:a:vendor:product:version:...
                                    cpe_parts = cpe_name.split(":")
                                    if len(cpe_parts) >= 5:
                                        cpe_prefix = ":".join(cpe_parts[:5])
                                        self.cpe_cache[product_name] = cpe_prefix
                                        logger.debug(f"Found CPE for {product_name}: {cpe_prefix}")
                                        return cpe_prefix

                    elif response.status == 403:
                        logger.warning("NVD API rate limit reached during CPE lookup")
                        await asyncio.sleep(30)

        except Exception as e:
            logger.debug(f"CPE lookup failed for {product_name}: {e}")

        self.cpe_cache[product_name] = None
        return None

    async def _query_nvd_cves(self, keyword: str = None, cpe_name: str = None,
                              version: str = None) -> List[Dict]:
        """Query NVD API for CVEs"""
        cves = []

        params = {
            "resultsPerPage": 100
        }

        if keyword:
            params["keywordSearch"] = keyword

        if cpe_name:
            # Build CPE match string with version if available
            if version:
                params["virtualMatchString"] = f"{cpe_name}:{version}"
            else:
                params["virtualMatchString"] = cpe_name

        # Only get CVEs from last 2 years for relevance
        two_years_ago = (datetime.now(timezone.utc) - timedelta(days=730)).strftime("%Y-%m-%dT00:00:00.000")
        params["pubStartDate"] = two_years_ago

        headers = {}
        if self.nvd_api_key:
            headers["apiKey"] = self.nvd_api_key

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    NVD_CVE_API_URL,
                    params=params,
                    headers=headers,
                    timeout=60
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        vulnerabilities = data.get("vulnerabilities", [])
                        logger.debug(f"NVD query '{keyword or cpe_name}': found {len(vulnerabilities)} CVEs")

                        for vuln in vulnerabilities:
                            cve = vuln.get("cve", {})
                            cves.append(self._parse_nvd_cve(cve))
                    elif response.status == 403:
                        logger.warning("NVD API rate limit reached, waiting...")
                        await asyncio.sleep(30)
                    else:
                        logger.warning(f"NVD API returned status {response.status}")

        except asyncio.TimeoutError:
            logger.error(f"Timeout querying NVD for {keyword or cpe_name}")
        except Exception as e:
            logger.error(f"Error querying NVD: {e}")

        return cves

    @staticmethod
    def _parse_nvd_cve(cve_data: Dict) -> Dict[str, Any]:
        """Parse NVD CVE response into our format"""
        cve_id = cve_data.get("id", "Unknown")

        # Get description (prefer English)
        description = "No description available"
        descriptions = cve_data.get("descriptions", [])
        for desc in descriptions:
            if desc.get("lang") == "en":
                description = desc.get("value", description)
                break

        # Get CVSS score and severity
        cvss_score = None
        severity = "medium"

        metrics = cve_data.get("metrics", {})

        # Try CVSS 3.1 first, then 3.0, then 2.0
        for cvss_version in ["cvssMetricV31", "cvssMetricV30", "cvssMetricV2"]:
            if cvss_version in metrics and metrics[cvss_version]:
                cvss_data = metrics[cvss_version][0].get("cvssData", {})
                cvss_score = cvss_data.get("baseScore")
                severity_str = cvss_data.get("baseSeverity", "").lower()
                if severity_str:
                    severity = severity_str
                break

        # Map CVSS score to severity if not provided
        if cvss_score and severity == "medium":
            if cvss_score >= 9.0:
                severity = "critical"
            elif cvss_score >= 7.0:
                severity = "high"
            elif cvss_score >= 4.0:
                severity = "medium"
            else:
                severity = "low"

        # Get affected versions from CPE configurations
        affected_versions = []
        fixed_versions = []
        affected_products = []

        configurations = cve_data.get("configurations", [])
        for cfg in configurations:
            for node in cfg.get("nodes", []):
                for cpe_match in node.get("cpeMatch", []):
                    if cpe_match.get("vulnerable", False):
                        cpe_uri = cpe_match.get("criteria", "")
                        # Extract product from CPE
                        cpe_parts = cpe_uri.split(":")
                        if len(cpe_parts) >= 5:
                            product = cpe_parts[4]
                            if product not in affected_products:
                                affected_products.append(product)

                        # Get version info
                        version_start = cpe_match.get("versionStartIncluding") or cpe_match.get("versionStartExcluding")
                        version_end = cpe_match.get("versionEndIncluding") or cpe_match.get("versionEndExcluding")

                        if version_start:
                            affected_versions.append(f">={version_start}")
                        if version_end:
                            affected_versions.append(f"<={version_end}")
                            # The fix is typically the next version after versionEndIncluding
                            if cpe_match.get("versionEndExcluding"):
                                fixed_versions.append(cpe_match.get("versionEndExcluding"))

        # Get references
        references = cve_data.get("references", [])
        external_url = None
        github_url = None

        for ref in references:
            url = ref.get("url", "")
            if "nvd.nist.gov" in url and not external_url:
                external_url = url
            elif "github.com" in url and not github_url:
                github_url = url

        # Default NVD URL
        if not external_url:
            external_url = f"https://nvd.nist.gov/vuln/detail/{cve_id}"

        # Get published date
        published = cve_data.get("published", "")

        return {
            "cve_id": cve_id,
            "title": description[:200] + "..." if len(description) > 200 else description,
            "description": description,
            "severity": severity,
            "cvss_score": cvss_score,
            "affected_versions": affected_versions[:10],  # Limit to 10
            "fixed_versions": fixed_versions[:5],
            "components": affected_products[:10],
            "published_date": published,
            "url": github_url,
            "external_url": external_url,
        }

    async def scan_kubernetes_components(self, cluster_info: Dict) -> List[Dict]:
        """Scan Kubernetes core components for CVEs"""
        cves_found = []

        k8s_version = cluster_info.get("kubernetes_version")
        if not k8s_version:
            logger.warning("Could not determine Kubernetes version, skipping K8s CVE scan")
            return cves_found

        logger.info(f"Scanning Kubernetes {k8s_version} for CVEs...")

        # Query NVD for Kubernetes CVEs using known CPE
        k8s_cves = await self._query_nvd_cves(
            cpe_name="cpe:2.3:a:kubernetes:kubernetes",
            version=k8s_version
        )

        for cve in k8s_cves:
            cve["components"] = ["kubernetes"] + cve.get("components", [])
            cve["cluster_version"] = k8s_version
            cves_found.append(cve)

        await asyncio.sleep(self.request_delay)

        # Scan container runtime
        for node in cluster_info.get("nodes", []):
            runtime = node.get("container_runtime", "")

            if "containerd" in runtime.lower():
                version_match = re.search(r'(\d+\.\d+\.\d+)', runtime)
                if version_match:
                    containerd_version = version_match.group(1)
                    logger.info(f"Scanning containerd {containerd_version} for CVEs...")
                    containerd_cves = await self._query_nvd_cves(
                        cpe_name="cpe:2.3:a:linuxfoundation:containerd",
                        version=containerd_version
                    )
                    for cve in containerd_cves:
                        cve["components"] = ["containerd"] + cve.get("components", [])
                        cve["cluster_version"] = containerd_version
                        cves_found.append(cve)
                    await asyncio.sleep(self.request_delay)
                    break

            elif "docker" in runtime.lower():
                version_match = re.search(r'(\d+\.\d+\.\d+)', runtime)
                if version_match:
                    docker_version = version_match.group(1)
                    logger.info(f"Scanning Docker {docker_version} for CVEs...")
                    docker_cves = await self._query_nvd_cves(
                        cpe_name="cpe:2.3:a:docker:docker",
                        version=docker_version
                    )
                    for cve in docker_cves:
                        cve["components"] = ["docker"] + cve.get("components", [])
                        cve["cluster_version"] = docker_version
                        cves_found.append(cve)
                    await asyncio.sleep(self.request_delay)
                    break

        return cves_found

    async def scan_container_images(self, images: List[Dict]) -> List[Dict]:
        """Scan container images for CVEs - dynamically looks up CPEs"""
        cves_found = []
        scanned_products: Set[str] = set()

        for image_info in images:
            image = image_info.get("image", "")
            parsed = self._parse_image_name(image)
            product = parsed.get("product", "")
            if product:
                product = product.lower()
            version = parsed.get("version")

            if not product or product in scanned_products:
                continue

            # Skip very short or generic names
            if len(product) <= 2:
                continue

            scanned_products.add(product)
            logger.info(f"Scanning {product} (version: {version or 'unknown'}) for CVEs...")

            # Try to find CPE dynamically
            cpe_prefix = await self._find_cpe_for_product(product)
            await asyncio.sleep(self.request_delay)

            if cpe_prefix:
                # Query with CPE for accurate results
                image_cves = await self._query_nvd_cves(
                    cpe_name=cpe_prefix,
                    version=version
                )
            else:
                # Fall back to keyword search
                image_cves = await self._query_nvd_cves(keyword=product)
                # Filter to only include CVEs that actually mention the product
                image_cves = [
                    cve for cve in image_cves
                    if product.lower() in cve.get("description", "").lower()
                ]

            for cve in image_cves:
                cve["components"] = [product] + cve.get("components", [])
                cve["cluster_version"] = version or "unknown"
                cve["description"] = f"Found in image: {image}. " + cve.get("description", "")
                cves_found.append(cve)

            await asyncio.sleep(self.request_delay)

        return cves_found

    async def scan_node_os(self, cluster_info: Dict) -> List[Dict]:
        """Scan node OS for CVEs - dynamically looks up CPEs"""
        cves_found = []
        scanned_os: Set[str] = set()

        # Common OS patterns to look for
        os_patterns = [
            ("ubuntu", "cpe:2.3:o:canonical:ubuntu_linux"),
            ("debian", "cpe:2.3:o:debian:debian_linux"),
            ("centos", "cpe:2.3:o:centos:centos"),
            ("red hat", "cpe:2.3:o:redhat:enterprise_linux"),
            ("rhel", "cpe:2.3:o:redhat:enterprise_linux"),
            ("fedora", "cpe:2.3:o:fedoraproject:fedora"),
            ("alpine", "cpe:2.3:o:alpinelinux:alpine_linux"),
            ("amazon linux", "cpe:2.3:o:amazon:linux"),
            ("suse", "cpe:2.3:o:suse:linux_enterprise_server"),
            ("arch", "cpe:2.3:o:archlinux:arch_linux"),
        ]

        for node in cluster_info.get("nodes", []):
            os_image = node.get("os_image", "").lower()

            for os_name, cpe_prefix in os_patterns:
                if os_name in os_image and os_name not in scanned_os:
                    scanned_os.add(os_name)

                    # Try to extract version
                    version_match = re.search(r'(\d+\.\d+(?:\.\d+)?)', os_image)
                    version = version_match.group(1) if version_match else None

                    logger.info(f"Scanning {os_name} (version: {version or 'unknown'}) for CVEs...")

                    os_cves = await self._query_nvd_cves(
                        cpe_name=cpe_prefix,
                        version=version
                    )

                    for cve in os_cves:
                        cve["components"] = [f"node-os:{os_name}"] + cve.get("components", [])
                        cve["cluster_version"] = version or "unknown"
                        cves_found.append(cve)

                    await asyncio.sleep(self.request_delay)

        return cves_found

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
                        text = await response.text()
                        logger.warning(f"Failed to report CVE {cve_data['cve_id']}: HTTP {response.status} - {text}")
        except Exception as e:
            logger.error(f"Error reporting CVE {cve_data['cve_id']}: {e}")

    async def report_progress(self, phase: str, percent: int, current_item: str = "",
                               total_items: int = 0, completed_items: int = 0, found_issues: int = 0):
        """Report scan progress to the backend for real-time UI updates"""
        progress_data = {
            "scanner": "cve",
            "phase": phase,
            "percent": percent,
            "current_item": current_item,
            "total_items": total_items,
            "completed_items": completed_items,
            "found_issues": found_issues
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.backend_url}/api/security/scan/progress",
                    json=progress_data,
                    timeout=10
                ) as response:
                    if response.status != 200:
                        logger.debug(f"Failed to report progress: HTTP {response.status}")
        except Exception as e:
            logger.debug(f"Error reporting progress: {e}")

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

    async def scan_cves(self):
        """Main CVE scanning logic - scans entire cluster with progress reporting"""
        logger.info("=" * 60)
        logger.info("Starting comprehensive cluster CVE scan...")
        logger.info("=" * 60)

        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        all_cves: List[Dict] = []
        seen_cve_ids: Set[str] = set()
        total_found = 0

        # Report scan start
        await self.report_progress("starting", 0, "Initializing scan...", 0, 0, 0)

        # 1. Get cluster information (5%)
        logger.info("Step 1: Gathering cluster information...")
        await self.report_progress("cluster_info", 5, "Gathering cluster information...", 0, 0, 0)
        cluster_info = self._get_cluster_info()

        # 2. Scan Kubernetes components (5-20%)
        logger.info("Step 2: Scanning Kubernetes components...")
        await self.report_progress("kubernetes", 10, "Scanning Kubernetes components...", 0, 0, total_found)
        k8s_cves = await self.scan_kubernetes_components(cluster_info)
        all_cves.extend(k8s_cves)
        total_found += len(k8s_cves)
        logger.info(f"  Found {len(k8s_cves)} Kubernetes component CVEs")
        await self.report_progress("kubernetes", 20, "Kubernetes scan complete", 0, 0, total_found)

        # 3. Get and scan container images (20-80%)
        logger.info("Step 3: Scanning container images...")
        images = self._get_all_container_images()
        total_images = len(images)

        # Filter to scannable images
        scannable_images = []
        for img_info in images:
            image = img_info.get("image", "")
            parsed = self._parse_image_name(image)
            product = parsed.get("product", "")
            if product and len(product) > 2:
                scannable_images.append((img_info, parsed))

        total_scannable = len(scannable_images)
        scanned_products: Set[str] = set()
        image_cves: List[Dict] = []

        for idx, (image_info, parsed) in enumerate(scannable_images):
            image = image_info.get("image", "")
            product = parsed.get("product", "")
            if product:
                product = product.lower()
            version = parsed.get("version")

            if product in scanned_products:
                continue

            scanned_products.add(product)

            # Calculate progress (20-80% range for images)
            progress_percent = 20 + int((idx / max(total_scannable, 1)) * 60)
            await self.report_progress(
                "images",
                progress_percent,
                f"Scanning {product}...",
                total_scannable,
                idx + 1,
                total_found
            )

            logger.info(f"Scanning {product} (version: {version or 'unknown'}) for CVEs...")

            # Try to find CPE dynamically
            cpe_prefix = await self._find_cpe_for_product(product)
            await asyncio.sleep(self.request_delay)

            if cpe_prefix:
                img_cves = await self._query_nvd_cves(cpe_name=cpe_prefix, version=version)
            else:
                img_cves = await self._query_nvd_cves(keyword=product)
                img_cves = [
                    cve for cve in img_cves
                    if product.lower() in cve.get("description", "").lower()
                ]

            for cve in img_cves:
                cve["components"] = [product] + cve.get("components", [])
                cve["cluster_version"] = version or "unknown"
                cve["description"] = f"Found in image: {image}. " + cve.get("description", "")
                image_cves.append(cve)

            total_found += len(img_cves)
            await asyncio.sleep(self.request_delay)

        all_cves.extend(image_cves)
        logger.info(f"  Found {len(image_cves)} container image CVEs")
        await self.report_progress("images", 80, "Image scan complete", total_scannable, total_scannable, total_found)

        # 4. Scan node OS (80-95%)
        logger.info("Step 4: Scanning node operating systems...")
        await self.report_progress("os", 85, "Scanning node operating systems...", 0, 0, total_found)
        os_cves = await self.scan_node_os(cluster_info)
        all_cves.extend(os_cves)
        total_found += len(os_cves)
        logger.info(f"  Found {len(os_cves)} node OS CVEs")
        await self.report_progress("os", 95, "OS scan complete", 0, 0, total_found)

        # 5. Report unique CVEs to backend (95-100%)
        logger.info("Step 5: Reporting CVEs to backend...")
        await self.report_progress("reporting", 97, "Reporting CVEs...", 0, 0, total_found)
        reported_count = 0

        for cve in all_cves:
            cve_id = cve.get("cve_id")
            if cve_id and cve_id not in seen_cve_ids:
                seen_cve_ids.add(cve_id)
                cve["timestamp"] = timestamp
                await self.report_cve(cve)
                reported_count += 1

        # Report completion
        await self.report_progress("complete", 100, "Scan complete!", 0, 0, reported_count)

        logger.info("=" * 60)
        logger.info(f"CVE scan completed!")
        logger.info(f"  Total unique CVEs found: {reported_count}")
        logger.info(f"  Kubernetes CVEs: {len(k8s_cves)}")
        logger.info(f"  Container image CVEs: {len(image_cves)}")
        logger.info(f"  Node OS CVEs: {len(os_cves)}")
        logger.info("=" * 60)

    async def start_scanning(self):
        """Start the CVE scanning loop"""
        logger.info(f"Starting CVE scanner (scan interval: {self.scan_interval}s)")
        logger.info(f"Backend URL: {self.backend_url}")
        logger.info(f"NVD API key configured: {'Yes' if self.nvd_api_key else 'No (rate limited)'}")

        self._init_kubernetes_client()

        while True:
            try:
                await self.clear_cves()
                await self.scan_cves()
                logger.info(f"Next CVE scan in {self.scan_interval}s")
            except Exception as e:
                logger.error(f"Error during CVE scan: {e}")
                import traceback
                logger.error(traceback.format_exc())

            await asyncio.sleep(self.scan_interval)