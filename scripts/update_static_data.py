from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mvv_delay_tracker.static.static_data import (
    download_static_files,
    write_trip_info_version,
)
from mvv_delay_tracker.static.static_stops import create_munich_stop_list


def main() -> None:
    """Download and write changed static GTFS files."""
    remote_files = download_static_files(
        include_stops=True,
        include_metadata=True,
    )
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    output_path = Path("data/static/trip_info.json")
    write_trip_info_version(remote_files, output_path, timestamp)

    munich_stops = create_munich_stop_list(remote_files["stops.txt"])
    munich_stops.to_csv("data/static/munich_stops.csv", index=False)
    print("Updated static GTFS trip information.")


if __name__ == "__main__":
    main()