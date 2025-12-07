import asyncio
import logging
import os
from services.security_scanner import SecurityScanner
from services.cve_scanner import CVEScanner


async def run_scanners():
    """Run both security and CVE scanners concurrently"""
    logger = logging.getLogger(__name__)

    # Initialize scanners
    security_scanner = SecurityScanner()
    cve_scanner = CVEScanner()

    # Check if CVE scanning is enabled (default: enabled)
    cve_enabled = os.getenv("CVE_SCAN_ENABLED", "true").lower() == "true"

    tasks = [security_scanner.start_scanning()]

    if cve_enabled:
        logger.info("CVE scanning is enabled")
        tasks.append(cve_scanner.start_scanning())
    else:
        logger.info("CVE scanning is disabled")

    # Run scanners concurrently
    await asyncio.gather(*tasks)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting Kure Security Scanner...")

    try:
        asyncio.run(run_scanners())
    except KeyboardInterrupt:
        logger.info("Shutting down security scanner...")


if __name__ == "__main__":
    main()