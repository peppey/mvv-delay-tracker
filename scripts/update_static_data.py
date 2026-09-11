from __future__ import annotations

from mvv_delay_tracker.static.static_data import (
    download_static_file,
    download_static_files,
    update_static_files,
)
from mvv_delay_tracker.static.static_stops import update_munich_stops


def main() -> None:
    """Download and write changed static GTFS files."""
    remote_files = download_static_files()
    changed_files = update_static_files(remote_files)
    stops_changed = update_munich_stops(download_static_file("stops.txt"))
    if stops_changed:
        changed_files.append("munich_stops.csv")

    if changed_files:
        print("Updated static GTFS data: " + ", ".join(changed_files))
    else:
        print("Static GTFS data is already up to date.")


if __name__ == "__main__":
    main()