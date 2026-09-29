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

    def request_stop(sig, frame):
        logger.info("Received termination signal %s, initiating shutdown...", sig)
        # A signal handler runs between bytecodes on the event loop thread, so it must never await
        # or raise. Schedule the coroutine and let the loop drain it on the next iteration.
        loop.call_soon_threadsafe(loop.create_task, daemon.stop())

    # SIGINT covers Ctrl+C on Windows and Ctrl+C on POSIX. SIGTERM is delivered by process
    # managers only on POSIX; Windows consoles raise SIGBREAK for Ctrl+Break instead.
    for signame in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, signame, None)
        if sig is not None:
            try:
                signal.signal(sig, request_stop)
            except (OSError, ValueError):
                logger.debug("Signal %s is not supported on this platform.", signame)

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
