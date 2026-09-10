from __future__ import annotations

import os

from mvv_delay_tracker.static_data import (
    download_static_files,
    find_changed_files,
)


def main() -> None:
    remote_files = download_static_files()
    changed_files = find_changed_files(remote_files)

    if changed_files:
        print("Static GTFS data changed: " + ", ".join(changed_files))
    else:
        print("Static GTFS data is unchanged.")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as output:
            output.write(f"changed={'true' if changed_files else 'false'}\n")


if __name__ == "__main__":
    main()