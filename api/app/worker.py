"""Background worker: periodically scans every package and sends notifications.

python -m app.worker          # run forever on SCAN_INTERVAL_MINUTES
python -m app.worker --once   # scan once and exit (cron / manual check)
"""

import argparse
import asyncio
import logging
import signal

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.services.scanner import scan_and_notify

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("vectana.worker")


async def run_forever() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scan_and_notify,
        "interval",
        minutes=settings.scan_interval_minutes,
        id="scan",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Worker started; scanning every %d minute(s)", settings.scan_interval_minutes)
    # Scan once at startup so a fresh deploy reports immediately.
    await scan_and_notify()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    scheduler.shutdown(wait=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="scan once and exit")
    args = parser.parse_args()
    if args.once:
        sent = asyncio.run(scan_and_notify())
        logger.info("Done (%d digest(s) sent)", sent)
    else:
        asyncio.run(run_forever())


if __name__ == "__main__":
    main()
