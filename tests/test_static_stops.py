import json

import pandas as pd

from mvv_delay_tracker.analysis.geographic import wgs84_to_utm32
from mvv_delay_tracker.static.static_stops import create_munich_stop_list


def test_create_munich_stop_list_filters_in_memory_stops(tmp_path):
    geojson_path = tmp_path / "munich.geojson"
    inside_x, inside_y = wgs84_to_utm32(47.0, 11.0)
    geojson_path.write_text(
        json.dumps({
            "features": [{
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [inside_x - 1000, inside_y - 1000],
                        [inside_x + 1000, inside_y - 1000],
                        [inside_x + 1000, inside_y + 1000],
                        [inside_x - 1000, inside_y + 1000],
                        [inside_x - 1000, inside_y - 1000],
                    ]],
                },
            }],
        }),
        encoding="utf-8",
    )

    stops = pd.DataFrame({
        "stop_id": ["inside", "outside"],
        "stop_name": ["Inside", "Outside"],
        "stop_lat": [47.0, 48.0],
        "stop_lon": [11.0, 11.0],
    }).to_csv(index=False).encode()

    result = create_munich_stop_list(
        stops,
        munich_geojson_path=str(geojson_path),
    )

    assert list(result["stop_id"]) == ["inside"]
