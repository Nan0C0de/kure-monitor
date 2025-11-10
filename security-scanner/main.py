import asyncio
import logging
from services.security_scanner import SecurityScanner


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    scanner = SecurityScanner()

    try:
        asyncio.run(scanner.start_scanning())
    except KeyboardInterrupt:
        logging.info("Shutting down security scanner...")


if __name__ == "__main__":
    main()