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
