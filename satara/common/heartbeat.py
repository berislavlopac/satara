"""A heartbeat file, touched at intervals to show the process is alive."""

import threading
import time
from pathlib import Path


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
