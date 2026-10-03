"""Run the queue consumer until the process is told to stop.

The consumer is built from the settings in the environment. While it runs, a heartbeat file
in the temporary directory is touched every 15 seconds, for a health check to look at. A stop
signal ends it once the batch of messages in hand is handled.
"""

import asyncio
import signal
import tempfile
from pathlib import Path

from satara.common.heartbeat import start_heartbeat
from satara.config import Settings
from satara.wiring import open_consumer

HEARTBEAT_FILE = Path(tempfile.gettempdir()) / "satara-consumer-alive"


async def main() -> None:
    """Run the consumer, with a heartbeat, until the process is told to stop."""
    start_heartbeat(HEARTBEAT_FILE)
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    async with open_consumer(Settings()) as consumer:
        await consumer.run(stop)


if __name__ == "__main__":
    asyncio.run(main())
