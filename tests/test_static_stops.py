import json
from pathlib import Path

import pandas as pd

from mvv_delay_tracker.static.static_stops import (
    create_munich_stops_csv,
    find_changed_munich_stops,
    update_munich_stops,
)


def make_geojson(path: Path) -> None:
    path.write_text(json.dumps({
        "features": [{
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [0, 0],
                    [10, 0],
                    [10, 10],
                    [0, 10],
                ]],
            },
        }],
    }))


def make_stops() -> bytes:
    return pd.DataFrame({
        "stop_name": ["Inside", "Outside"],
        "stop_lat": [1.0, 20.0],
        "stop_lon": [1.0, 20.0],
    }).to_csv(index=False).encode("utf-8")


def test_create_munich_stops_csv_filters_stops(monkeypatch, tmp_path):
    geojson_path = tmp_path / "munich.geojson"
    make_geojson(geojson_path)
    monkeypatch.setattr(
        "mvv_delay_tracker.static.static_stops.wgs84_to_utm32",
        lambda latitude, longitude: (latitude, longitude),
    )

    result = pd.read_csv(
        __import__("io").BytesIO(
            create_munich_stops_csv(make_stops(), geojson_path)
        )
    )

    assert list(result["stop_name"]) == ["Inside"]
    assert list(result["inside_munich"]) == [True]


def test_update_munich_stops_only_writes_changes(monkeypatch, tmp_path):
    geojson_path = tmp_path / "munich.geojson"
    output_path = tmp_path / "munich_stops.csv"
    make_geojson(geojson_path)
    monkeypatch.setattr(
        "mvv_delay_tracker.static.static_stops.wgs84_to_utm32",
        lambda latitude, longitude: (latitude, longitude),
    )

    assert update_munich_stops(make_stops(), output_path, geojson_path)
    assert not find_changed_munich_stops(make_stops(), output_path, geojson_path)
    assert not update_munich_stops(make_stops(), output_path, geojson_path)


def test_create_munich_stops_includes_all_stops_of_relevant_lines(
    monkeypatch, tmp_path
):
    geojson_path = tmp_path / "munich.geojson"
    lines_path = tmp_path / "munich_lines.csv"
    make_geojson(geojson_path)
    monkeypatch.setattr(
        "mvv_delay_tracker.static.static_stops.wgs84_to_utm32",
        lambda latitude, longitude: (latitude, longitude),
    )

    stops = pd.DataFrame({
        "stop_id": ["munich", "petershausen", "other"],
        "stop_name": ["Munich", "Petershausen", "Other"],
        "stop_lat": [1.0, 20.0, 20.0],
        "stop_lon": [1.0, 20.0, 20.0],
    }).to_csv(index=False).encode("utf-8")
    routes = pd.DataFrame({
        "route_id": ["s2", "sev", "other"],
        "route_short_name": ["S2", "SEV S2", "X"],
        "route_long_name": ["S-Bahn", "Schienenersatzverkehr S2", "Other"],
        "agency_id": ["mvg-sbahn", "mvg-sbahn", "other-agency"],
        "route_type": ["3", "3", "3"],
    }).to_csv(index=False).encode("utf-8")
    trips = pd.DataFrame({
        "trip_id": ["trip-s2", "trip-sev", "trip-other"],
        "route_id": ["s2", "sev", "other"],
    }).to_csv(index=False).encode("utf-8")
    stop_times = pd.DataFrame({
        "trip_id": ["trip-s2", "trip-s2", "trip-sev", "trip-other"],
        "stop_id": ["munich", "petershausen", "munich", "other"],
    }).to_csv(index=False).encode("utf-8")
    agency = pd.DataFrame({
        "agency_id": ["mvg-sbahn", "other-agency"],
        "agency_name": ["DB S-Bahn München", "Other Verkehrsbetrieb"],
    }).to_csv(index=False).encode("utf-8")
    pd.DataFrame({"line": ["S2"], "mode": ["S-Bahn"]}).to_csv(
        lines_path, index=False
    )

    result = pd.read_csv(
        __import__("io").BytesIO(
            create_munich_stops_csv(
                stops,
                geojson_path,
                routes,
                trips,
                stop_times,
                agency,
                lines_path,
            )
        )
    )

    assert set(result["stop_name"]) == {"Munich", "Petershausen"}


def test_create_munich_stops_ignores_same_named_line_from_other_agency(
    monkeypatch, tmp_path
):
    """A route_short_name collision from an unrelated agency (e.g. a
    cross-border coach line reusing "S2") must not pull in its far-away
    stops just because it also touches Munich."""
    geojson_path = tmp_path / "munich.geojson"
    lines_path = tmp_path / "munich_lines.csv"
    make_geojson(geojson_path)
    monkeypatch.setattr(
        "mvv_delay_tracker.static.static_stops.wgs84_to_utm32",
        lambda latitude, longitude: (latitude, longitude),
    )

    stops = pd.DataFrame({
        "stop_id": ["munich", "petershausen", "budapest"],
        "stop_name": ["Munich", "Petershausen", "Budapest"],
        "stop_lat": [1.0, 20.0, 47.0],
        "stop_lon": [1.0, 20.0, 19.0],
    }).to_csv(index=False).encode("utf-8")
    routes = pd.DataFrame({
        "route_id": ["s2", "impostor"],
        "route_short_name": ["S2", "S2"],
        "route_long_name": ["S-Bahn", "Fernbus Munich-Budapest"],
        "agency_id": ["mvg-sbahn", "fernbus-agency"],
        "route_type": ["3", "3"],
    }).to_csv(index=False).encode("utf-8")
    trips = pd.DataFrame({
        "trip_id": ["trip-s2", "trip-impostor"],
        "route_id": ["s2", "impostor"],
    }).to_csv(index=False).encode("utf-8")
    stop_times = pd.DataFrame({
        "trip_id": ["trip-s2", "trip-s2", "trip-impostor", "trip-impostor"],
        "stop_id": ["munich", "petershausen", "munich", "budapest"],
    }).to_csv(index=False).encode("utf-8")
    agency = pd.DataFrame({
        "agency_id": ["mvg-sbahn", "fernbus-agency"],
        "agency_name": ["DB S-Bahn München", "Fernbus GmbH"],
    }).to_csv(index=False).encode("utf-8")
    pd.DataFrame({"line": ["S2"], "mode": ["S-Bahn"]}).to_csv(
        lines_path, index=False
    )

    result = pd.read_csv(
        __import__("io").BytesIO(
            create_munich_stops_csv(
                stops,
                geojson_path,
                routes,
                trips,
                stop_times,
                agency,
                lines_path,
            )
        )
    )

    assert set(result["stop_name"]) == {"Munich", "Petershausen"}

