from __future__ import annotations

import os

from mvv_delay_tracker.static.static_data import (
    download_static_files,
    trip_info_version_changed,
)


def main() -> None:
    """Check the remote GTFS files and publish the GitHub Actions result."""
    remote_files = download_static_files(include_metadata=True)
    changed = trip_info_version_changed(remote_files)

    if changed:
        print("Static GTFS trip information changed.")
    else:
        print("Static GTFS trip information is unchanged.")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as output:
            output.write(f"changed={'true' if changed else 'false'}\n")


if __name__ == "__main__":
    main()