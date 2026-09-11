from __future__ import annotations

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


def main() -> None:
    """Download and write changed static GTFS files."""
    try:
        remote_files = download_static_files(include_stops=True)
        required_files = (*FILES_TO_UPDATE, "stops.txt")
        if not remote_files and not all(
            (STATIC_DATA_DIR / filename).exists()
            for filename in required_files
        ):
            remote_files = download_static_files(
                include_stops=True,
                conditional=False,
            )
        if remote_files:
            stops_bytes = remote_files.pop("stops.txt")
            changed_files = update_static_files(remote_files)
            stops_changed = update_munich_stops(stops_bytes)
            if stops_changed:
                changed_files.append("munich_stops.csv")
        else:
            changed_files = []

        if changed_files:
            print("Updated static GTFS data: " + ", ".join(changed_files))
        else:
            print("Static GTFS data is already up to date.")

        report = run_data_completeness_check()
        print(f"Data completeness periods: {len(report)}")
    finally:
        if os.environ.get("KEEP_TEMPORARY_STATIC_FILES") != "true":
            remove_temporary_static_files()


if __name__ == "__main__":
    main()