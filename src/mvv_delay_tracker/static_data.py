from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import requests


STATIC_DATA_URL = "https://download.gtfs.de/germany/nv_free/latest.zip"
STATIC_DATA_DIR = Path("data/static")
FILES_TO_UPDATE = ("routes.txt", "trips.txt")


def download_static_files(
    url: str = STATIC_DATA_URL,
) -> dict[str, bytes]:
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    with ZipFile(BytesIO(response.content)) as archive:
        archive_files = {
            Path(name).name: name
            for name in archive.namelist()
            if not name.endswith("/")
        }
        missing_files = [
            filename
            for filename in FILES_TO_UPDATE
            if filename not in archive_files
        ]
        if missing_files:
            raise ValueError(
                "The GTFS archive is missing: "
                + ", ".join(missing_files)
            )

        return {
            filename: archive.read(archive_files[filename])
            for filename in FILES_TO_UPDATE
        }


def find_changed_files(
    remote_files: dict[str, bytes],
    data_dir: Path = STATIC_DATA_DIR,
) -> list[str]:
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
    changed_files = find_changed_files(remote_files, data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    for filename in changed_files:
        target = data_dir / filename
        temporary_target = target.with_suffix(target.suffix + ".tmp")
        temporary_target.write_bytes(remote_files[filename])
        temporary_target.replace(target)

    return changed_files
