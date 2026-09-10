from __future__ import annotations

from mvv_delay_tracker.static_data import (
    download_static_files,
    update_static_files,
)


def main() -> None:
    remote_files = download_static_files()
    changed_files = update_static_files(remote_files)

    if changed_files:
        print("Updated static GTFS data: " + ", ".join(changed_files))
    else:
        print("Static GTFS data is already up to date.")


if __name__ == "__main__":
    main()