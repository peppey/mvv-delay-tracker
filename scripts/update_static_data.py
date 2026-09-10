from __future__ import annotations

from mvv_delay_tracker.static.static_data import (
    download_static_files,
    update_static_files,
)
from mvv_delay_tracker.static.static_stops import create_munich_stop_list


def main() -> None:
    """Download and write changed static GTFS files."""
    remote_files = download_static_files(include_stops=True)
    changed_files = update_static_files(remote_files)

    if changed_files:
        munich_stops = create_munich_stop_list(remote_files["stops.txt"])
        munich_stops.to_csv("data/static/munich_stops.csv", index=False)
        print("Updated static GTFS data: " + ", ".join(changed_files))
    else:
        print("Static GTFS data is already up to date.")


if __name__ == "__main__":
    main()