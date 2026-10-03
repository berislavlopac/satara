"""Run the queue consumer until the process is told to stop.

The consumer is built from the settings in the environment. While it runs, a heartbeat file
in the temporary directory is touched every 15 seconds, for a health check to look at. A stop
signal ends it once the batch of messages in hand is handled.
"""

import asyncio
import signal
import tempfile
import threading
import time
from pathlib import Path

from satara.common.logging import get_logger
from satara.config import Settings
from satara.wiring import open_consumer

HEARTBEAT_FILE = Path(tempfile.gettempdir()) / "satara-consumer-alive"
"""The file the consumer touches every 15 seconds while it runs, for a health check to test."""

log = get_logger("satara.consumer")


def start_heartbeat(path: Path, interval: float = 15.0) -> None:
    """Touch `path` every `interval` seconds from a daemon thread, for the process's lifetime.

    The thread runs apart from the event loop, so a long piece of work does not stop it.

    Args:
        path: The file to touch.
        interval: The seconds between touches.
    """

    def beat() -> None:
        while True:
            path.touch()
            time.sleep(interval)

    threading.Thread(target=beat, daemon=True, name="heartbeat").start()


async def main(settings: Settings) -> None:
    """Run the consumer, with a heartbeat, until the process is told to stop."""
    start_heartbeat(HEARTBEAT_FILE)
    stop = asyncio.Event()

    def request_stop() -> None:
        log.info("Stop signal received; finishing the current batch.")
        stop.set()

    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, request_stop)
    async with open_consumer(settings) as consumer:
        await consumer.run(stop)


if __name__ == "__main__":
    settings = Settings()
    # Debug mode reports coroutines never awaited and steps that block the event loop.
    asyncio.run(main(settings), debug=settings.DEBUG)
