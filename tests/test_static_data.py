from pathlib import Path
from io import BytesIO
from unittest.mock import Mock
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from mvv_delay_tracker.static.static_data import (
    create_trip_info_version,
    download_static_files,
    find_changed_files,
    update_static_files,
)


def make_archive(
    routes: bytes = b"routes",
    trips: bytes | None = b"trips",
    stops: bytes | None = None,
) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("gtfs/routes.txt", routes)
        if trips is not None:
            archive.writestr("gtfs/trips.txt", trips)
        if stops is not None:
            archive.writestr("gtfs/stops.txt", stops)
    return buffer.getvalue()


def test_download_static_files(monkeypatch):
    class Response:
        content = make_archive()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "mvv_delay_tracker.static.static_data.requests.get",
        Mock(return_value=Response()),
    )

    assert download_static_files("https://example.test/feed.zip") == {
        "routes.txt": b"routes",
        "trips.txt": b"trips",
    }


def test_download_static_files_rejects_missing_file(monkeypatch):
    class Response:
        content = make_archive(trips=None)

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "mvv_delay_tracker.static.static_data.requests.get",
        Mock(return_value=Response()),
    )

    with pytest.raises(ValueError, match="trips.txt"):
        download_static_files()


def test_download_static_files_can_include_stops(monkeypatch):
    class Response:
        content = make_archive(stops=b"stops")

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "mvv_delay_tracker.static.static_data.requests.get",
        Mock(return_value=Response()),
    )

    assert download_static_files(include_stops=True)["stops.txt"] == b"stops"


def test_find_changed_files(tmp_path: Path):
    (tmp_path / "routes.txt").write_bytes(b"old routes")
    (tmp_path / "trips.txt").write_bytes(b"trips")

    assert find_changed_files(
        {"routes.txt": b"routes", "trips.txt": b"trips"},
        tmp_path,
    ) == ["routes.txt"]


def test_update_static_files_only_writes_changed_files(tmp_path: Path):
    (tmp_path / "routes.txt").write_bytes(b"old routes")
    (tmp_path / "trips.txt").write_bytes(b"trips")

    changed_files = update_static_files(
        {"routes.txt": b"routes", "trips.txt": b"trips"},
        tmp_path,
    )

    assert changed_files == ["routes.txt"]
    assert (tmp_path / "routes.txt").read_bytes() == b"routes"
    assert (tmp_path / "trips.txt").read_bytes() == b"trips"


def test_create_trip_info_version_includes_agency_and_service_calendar():
    files = {
        "routes.txt": (
            b"route_id,route_short_name,agency_id\n"
            b"r1,S1,a1\n"
        ),
        "trips.txt": b"trip_id,route_id,service_id\nt1,r1,s1\n",
        "agency.txt": b"agency_id,agency_name\na1,Agency One\n",
        "calendar.txt": (
            b"monday,tuesday,wednesday,thursday,friday,saturday,sunday,"
            b"start_date,end_date,service_id\n"
            b"1,0,0,0,0,0,0,20260901,20260930,s1\n"
        ),
        "calendar_dates.txt": (
            b"service_id,exception_type,date\n"
            b"s1,1,20260910\n"
        ),
    }

    version = create_trip_info_version(files)

    assert version["trips"]["ids"] == ["t1"]
    assert version["lines"] == ["S1"]
    assert version["agencies"] == [
        {"agency_id": "a1", "agency_name": "Agency One"}
    ]
    assert version["service_ids"] == ["s1"]
    assert version["services"]["s1"]["weekdays"] == ["monday"]
    assert version["services"]["s1"]["added_dates"] == ["20260910"]
