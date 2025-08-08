import asyncio
import logging
from pod_monitor import PodMonitor


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    monitor = PodMonitor()

    try:
        asyncio.run(monitor.start_monitoring())
    except KeyboardInterrupt:
        logging.info("Shutting down pod monitor...")


if __name__ == "__main__":
    main()