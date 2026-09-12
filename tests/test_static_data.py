from pathlib import Path
from io import BytesIO
from unittest.mock import Mock
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from mvv_delay_tracker.static.static_data import (
    download_static_files,
    find_changed_files,
    update_static_files,
    remove_temporary_static_files,
)


def make_archive(
    agency: bytes = b"agency",
    routes: bytes = b"routes",
    trips: bytes | None = b"trips",
) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("gtfs/agency.txt", agency)
        archive.writestr("gtfs/routes.txt", routes)
        if trips is not None:
            archive.writestr("gtfs/trips.txt", trips)
        archive.writestr("gtfs/stop_times.txt", b"stop times")
        archive.writestr("gtfs/calendar.txt", b"calendar")
        archive.writestr("gtfs/calendar_dates.txt", b"calendar dates")
        archive.writestr("gtfs/stops.txt", b"stops")
    return buffer.getvalue()


def test_download_static_files(monkeypatch):
    class Response:
        status_code = 200
        headers = {}
        content = make_archive()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "mvv_delay_tracker.static.static_data.requests.get",
        Mock(return_value=Response()),
    )

    assert download_static_files("https://example.test/feed.zip") == {
        "agency.txt": b"agency",
        "routes.txt": b"routes",
        "trips.txt": b"trips",
        "stop_times.txt": b"stop times",
        "calendar.txt": b"calendar",
        "calendar_dates.txt": b"calendar dates",
    }


def test_download_static_files_can_include_stops(monkeypatch, tmp_path):
    class Response:
        status_code = 200
        headers = {}
        content = make_archive()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "mvv_delay_tracker.static.static_data.requests.get",
        Mock(return_value=Response()),
    )

    files = download_static_files(
        "https://example.test/feed.zip",
        include_stops=True,
        metadata_path=tmp_path / ".gtfs_metadata.json",
    )

    assert files["stops.txt"] == b"stops"


def test_download_static_files_uses_conditional_request(monkeypatch, tmp_path):
    metadata_path = tmp_path / ".gtfs_metadata.json"
    metadata_path.write_text(
        '{"etag": "feed-v1", "last_modified": "yesterday"}',
        encoding="utf-8",
    )

    class Response:
        status_code = 304
        headers = {}

        def raise_for_status(self):
            pass

    request = Mock(return_value=Response())
    monkeypatch.setattr(
        "mvv_delay_tracker.static.static_data.requests.get",
        request,
    )

    assert download_static_files(
        "https://example.test/feed.zip",
        metadata_path=metadata_path,
    ) == {}
    assert request.call_args.kwargs["headers"] == {
        "If-None-Match": "feed-v1",
        "If-Modified-Since": "yesterday",
    }


def test_download_static_files_rejects_missing_file(monkeypatch):
    class Response:
        status_code = 200
        headers = {}
        content = make_archive(trips=None)

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "mvv_delay_tracker.static.static_data.requests.get",
        Mock(return_value=Response()),
    )

    with pytest.raises(ValueError, match="trips.txt"):
        download_static_files()


def test_find_changed_files(tmp_path: Path):
    (tmp_path / "routes.txt").write_bytes(b"old routes")
    (tmp_path / "trips.txt").write_bytes(b"trips")

    assert find_changed_files(
        {
            "agency.txt": b"agency",
            "routes.txt": b"routes",
            "trips.txt": b"trips",
        },
        tmp_path,
    ) == ["agency.txt", "routes.txt"]


def test_update_static_files_only_writes_changed_files(tmp_path: Path):
    (tmp_path / "routes.txt").write_bytes(b"old routes")
    (tmp_path / "trips.txt").write_bytes(b"trips")

    changed_files = update_static_files(
        {
            "agency.txt": b"agency",
            "routes.txt": b"routes",
            "trips.txt": b"trips",
        },
        tmp_path,
    )

    assert changed_files == ["agency.txt", "routes.txt"]
    assert (tmp_path / "agency.txt").read_bytes() == b"agency"
    assert (tmp_path / "routes.txt").read_bytes() == b"routes"
    assert (tmp_path / "trips.txt").read_bytes() == b"trips"


def test_remove_temporary_static_files(tmp_path: Path):
    (tmp_path / "stop_times.txt").write_bytes(b"stop times")
    (tmp_path / "calendar.txt").write_bytes(b"calendar")
    (tmp_path / "calendar_dates.txt").write_bytes(b"calendar dates")
    (tmp_path / "routes.txt").write_bytes(b"routes")

    remove_temporary_static_files(tmp_path)

    assert not (tmp_path / "stop_times.txt").exists()
    assert not (tmp_path / "calendar.txt").exists()
    assert not (tmp_path / "calendar_dates.txt").exists()
    assert (tmp_path / "routes.txt").exists()
