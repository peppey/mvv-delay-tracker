from pathlib import Path
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from mvv_delay_tracker.static_data import (
    download_static_files,
    find_changed_files,
    update_static_files,
)


def make_archive(
    routes: bytes = b"routes",
    trips: bytes | None = b"trips",
) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("gtfs/routes.txt", routes)
        if trips is not None:
            archive.writestr("gtfs/trips.txt", trips)
        archive.writestr("gtfs/stops.txt", b"stops")
    return buffer.getvalue()


def test_download_static_files(monkeypatch):
    class Response:
        content = make_archive()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(
        "mvv_delay_tracker.static_data.requests.get",
        lambda url, timeout: Response(),
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
        "mvv_delay_tracker.static_data.requests.get",
        lambda url, timeout: Response(),
    )

    with pytest.raises(ValueError, match="trips.txt"):
        download_static_files()


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
