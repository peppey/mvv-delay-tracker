from __future__ import annotations

import logging
import os

from mvv_delay_tracker.static.static_data import (
    FILES_TO_UPDATE,
    STATIC_DATA_DIR,
    download_static_files,
    remove_temporary_static_files,
    update_static_files,
)
from mvv_delay_tracker.static.static_stops import update_munich_stops
from mvv_delay_tracker.realtime.data_completeness import (
    run_data_completeness_check,
)


logger = logging.getLogger(__name__)


def main() -> None:
    """Download and write changed static GTFS files."""
    try:
        logger.info("Checking for new static GTFS data...")
        remote_files = download_static_files(include_stops=True)
        required_files = (*FILES_TO_UPDATE, "munich_stops.csv")
        if not remote_files and not all(
            (STATIC_DATA_DIR / filename).exists()
            for filename in required_files
        ):
            logger.info("No local static data found, forcing a full download...")
            remote_files = download_static_files(
                include_stops=True,
                conditional=False,
            )
        if remote_files:
            logger.info("New static GTFS data downloaded, writing changed files...")
            stops_bytes = remote_files.pop("stops.txt")
            changed_files = update_static_files(remote_files)
            stops_changed = update_munich_stops(stops_bytes)
            if stops_changed:
                changed_files.append("munich_stops.csv")
        else:
            changed_files = []

        if changed_files:
            logger.info("Updated static GTFS data: %s", ", ".join(changed_files))
        else:
            logger.info("Static GTFS data is already up to date.")

        logger.info("Running data completeness check...")
        report = run_data_completeness_check()
        logger.info("Data completeness periods: %d", len(report))
    finally:
        if os.environ.get("KEEP_TEMPORARY_STATIC_FILES") != "true":
            remove_temporary_static_files()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    main()