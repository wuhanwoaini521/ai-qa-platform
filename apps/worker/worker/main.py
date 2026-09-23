from __future__ import annotations

import asyncio
import logging
import signal

from worker.daemon import WorkerDaemon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker")


def main() -> None:
    daemon = WorkerDaemon()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def handle_signal(sig, frame):
        logger.info("Received termination signal %s, initiating shutdown...", sig)
        loop.create_task(daemon.stop())

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    async def run():
        await daemon.start()
        while daemon._running:
            await asyncio.sleep(1.0)

    try:
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(daemon.stop())
        loop.close()
        logger.info("Worker process exited cleanly.")


if __name__ == "__main__":
    main()
