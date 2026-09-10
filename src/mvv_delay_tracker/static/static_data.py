from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import requests


STATIC_DATA_URL = "https://download.gtfs.de/germany/nv_free/latest.zip"
STATIC_DATA_DIR = Path("data/static")
FILES_TO_UPDATE = ("routes.txt", "trips.txt")
TRIP_INFO_FILES = (
    "routes.txt",
    "trips.txt",
    "agency.txt",
    "calendar.txt",
    "calendar_dates.txt",
)
STOPS_FILE = "stops.txt"


def download_static_files(
    url: str = STATIC_DATA_URL,
    include_stops: bool = False,
    include_metadata: bool = False,
) -> dict[str, bytes]:
    """Download the selected GTFS files from the remote archive."""
    response = requests.get(url, timeout=120)
    response.raise_for_status()

    archive_buffer = BytesIO(response.content)
    with ZipFile(archive_buffer) as archive:
        archive_files = {
            Path(name).name: name
            for name in archive.namelist()
            if not name.endswith("/")
        }
        requested_files = (
            TRIP_INFO_FILES if include_metadata else FILES_TO_UPDATE
        ) + (
            (STOPS_FILE,) if include_stops else ()
        )
        missing_files = [
            filename
            for filename in requested_files
            if filename not in archive_files
        ]
        if missing_files:
            raise ValueError(
                "The GTFS archive is missing: "
                + ", ".join(missing_files)
            )

        return {
            filename: archive.read(archive_files[filename])
            for filename in requested_files
        }


def find_changed_files(
    remote_files: dict[str, bytes],
    data_dir: Path = STATIC_DATA_DIR,
) -> list[str]:
    """Return remote files that are missing or differ locally."""
    return [
        filename
        for filename in FILES_TO_UPDATE
        if not (data_dir / filename).exists()
        or (data_dir / filename).read_bytes() != remote_files[filename]
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


def create_trip_info_version(
    remote_files: dict[str, bytes],
) -> dict[str, object]:
    """Create one compact, dated GTFS trip-information version.

    Each trip stores its route and agency metadata plus ``service_id``.
    The referenced service entry contains the regular weekdays and date
    exceptions needed to validate a realtime ``start_date``.
    """
    routes = pd.read_csv(
        BytesIO(remote_files["routes.txt"]),
        dtype={"route_id": str, "agency_id": str},
        usecols=["route_id", "route_short_name", "agency_id"],
    )
    trips = pd.read_csv(
        BytesIO(remote_files["trips.txt"]),
        dtype={"trip_id": str, "route_id": str, "service_id": str},
        usecols=["trip_id", "route_id", "service_id"],
    )
    agencies = pd.read_csv(
        BytesIO(remote_files["agency.txt"]),
        dtype={"agency_id": str},
        usecols=["agency_id", "agency_name"],
    )
    calendar = pd.read_csv(
        BytesIO(remote_files["calendar.txt"]),
        dtype=str,
    )
    calendar_dates = pd.read_csv(
        BytesIO(remote_files["calendar_dates.txt"]),
        dtype=str,
    )

    route_info = routes.merge(agencies, on="agency_id", how="left")
    trip_rows = trips.merge(route_info, on="route_id", how="inner")
    lines = sorted(trip_rows["route_short_name"].dropna().unique())
    line_indexes = {line: index for index, line in enumerate(lines)}
    agency_rows = (
        trip_rows[["agency_id", "agency_name"]]
        .drop_duplicates()
        .sort_values("agency_id")
        .to_dict("records")
    )
    agency_indexes = {
        row["agency_id"]: index
        for index, row in enumerate(agency_rows)
    }
    service_ids = sorted(trip_rows["service_id"].unique())
    service_indexes = {
        service_id: index
        for index, service_id in enumerate(service_ids)
    }

    weekday_columns = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]
    services = {}
    for row in calendar.to_dict("records"):
        services[row["service_id"]] = {
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "weekdays": [
                weekday
                for weekday in weekday_columns
                if row[weekday] == "1"
            ],
            "added_dates": [],
            "removed_dates": [],
        }

    for row in calendar_dates.to_dict("records"):
        service = services.setdefault(
            row["service_id"],
            {
                "start_date": None,
                "end_date": None,
                "weekdays": [],
                "added_dates": [],
                "removed_dates": [],
            },
        )
        target = (
            "added_dates"
            if row["exception_type"] == "1"
            else "removed_dates"
        )
        service[target].append(row["date"])

    return {
        "trips": {
            "ids": trip_rows["trip_id"].tolist(),
            "line_index": [
                line_indexes[line]
                for line in trip_rows["route_short_name"]
            ],
            "agency_index": [
                agency_indexes[agency_id]
                for agency_id in trip_rows["agency_id"]
            ],
            "service_index": [
                service_indexes[service_id]
                for service_id in trip_rows["service_id"]
            ],
        },
        "lines": lines,
        "agencies": agency_rows,
        "service_ids": service_ids,
        "services": services,
    }


def write_trip_info_version(
    remote_files: dict[str, bytes],
    output_path: Path,
    timestamp: str,
) -> None:
    """Add a timestamped trip-information version to a JSON file."""
    if output_path.exists():
        trip_info_document = json.loads(
            output_path.read_text(encoding="utf-8")
        )
    else:
        trip_info_document = {"versions": {}}

    trip_info_document.setdefault("versions", {})[timestamp] = (
        create_trip_info_version(remote_files)
    )
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(
            trip_info_document,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    temporary_path.replace(output_path)


def trip_info_version_changed(
    remote_files: dict[str, bytes],
    output_path: Path = STATIC_DATA_DIR / "trip_info.json",
) -> bool:
    """Return whether the downloaded metadata differs from the newest version."""
    if not output_path.exists():
        return True
    document = json.loads(output_path.read_text(encoding="utf-8"))
    versions = document.get("versions", {})
    if not versions:
        return True
    newest_timestamp = max(versions)
    return versions[newest_timestamp] != create_trip_info_version(
        remote_files
    )
