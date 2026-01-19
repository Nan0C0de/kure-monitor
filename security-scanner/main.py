import asyncio
import logging
from services.security_scanner import SecurityScanner


async def run_scanner():
    """Run the security scanner"""
    security_scanner = SecurityScanner()
    await security_scanner.start_scanning()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting Kure Security Scanner...")

    try:
        asyncio.run(run_scanner())
    except KeyboardInterrupt:
        logger.info("Shutting down security scanner...")


if __name__ == "__main__":
    main()
