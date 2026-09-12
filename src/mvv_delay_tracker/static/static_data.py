from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import requests


STATIC_DATA_URL = "https://download.gtfs.de/germany/nv_free/latest.zip"
STATIC_DATA_DIR = Path("data/static")
STATIC_DATA_METADATA_PATH = STATIC_DATA_DIR / ".gtfs_metadata.json"
FILES_TO_UPDATE = (
    "agency.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
    "calendar.txt",
    "calendar_dates.txt",
)
TEMPORARY_FILES = (
    "stop_times.txt",
    "calendar.txt",
    "calendar_dates.txt",
)


def download_static_files(
    url: str = STATIC_DATA_URL,
    include_stops: bool = False,
    metadata_path: Path = STATIC_DATA_METADATA_PATH,
    conditional: bool = True,
) -> dict[str, bytes]:
    """Download the selected GTFS files from the remote archive."""
    request_headers = {}
    if conditional and metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("etag"):
            request_headers["If-None-Match"] = metadata["etag"]
        if metadata.get("last_modified"):
            request_headers["If-Modified-Since"] = metadata["last_modified"]

    response = requests.get(url, headers=request_headers, timeout=120)
    response.raise_for_status()
    if response.status_code == 304:
        return {}

    response_metadata = {
        key: response.headers[key]
        for key in ("ETag", "Last-Modified")
        if key in response.headers
    }
    if response_metadata:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(
                {
                    "etag": response_metadata.get("ETag"),
                    "last_modified": response_metadata.get("Last-Modified"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    archive_buffer = BytesIO(response.content)
    with ZipFile(archive_buffer) as archive:
        archive_files = {
            Path(name).name: name
            for name in archive.namelist()
            if not name.endswith("/")
        }
        filenames = FILES_TO_UPDATE + (("stops.txt",) if include_stops else ())
        missing_files = [
            filename
            for filename in filenames
            if filename not in archive_files
        ]
        if missing_files:
            raise ValueError(
                "The GTFS archive is missing: "
                + ", ".join(missing_files)
            )

        return {
            filename: archive.read(archive_files[filename])
            for filename in filenames
        }


def download_static_file(
    filename: str,
    url: str = STATIC_DATA_URL,
) -> bytes:
    """Download one file from the static GTFS archive."""
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    with ZipFile(BytesIO(response.content)) as archive:
        archive_files = {
            Path(name).name: name
            for name in archive.namelist()
            if not name.endswith("/")
        }
        if filename not in archive_files:
            raise ValueError(
                f"The GTFS archive is missing: {filename}"
            )
        return archive.read(archive_files[filename])


def find_changed_files(
    remote_files: dict[str, bytes],
    data_dir: Path = STATIC_DATA_DIR,
) -> list[str]:
    """Return remote files that are missing or differ locally."""
    return [
        filename
        for filename, content in remote_files.items()
        if not (data_dir / filename).exists()
        or (data_dir / filename).read_bytes() != content
    ]


def update_static_files(
    remote_files: dict[str, bytes],
    data_dir: Path = STATIC_DATA_DIR,
) -> list[str]:
    """Write changed GTFS files and return their names."""
    changed_files = find_changed_files(remote_files, data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    for filename in changed_files:
        target = data_dir / filename
        temporary_target = target.with_suffix(target.suffix + ".tmp")
        temporary_target.write_bytes(remote_files[filename])
        temporary_target.replace(target)

    return changed_files


def remove_temporary_static_files(
    data_dir: Path = STATIC_DATA_DIR,
) -> None:
    """Remove GTFS files that are only needed during completeness checks."""
    for filename in TEMPORARY_FILES:
        (data_dir / filename).unlink(missing_ok=True)