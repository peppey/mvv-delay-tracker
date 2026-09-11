from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pandas as pd

from mvv_delay_tracker.analysis.geographic import wgs84_to_utm32


def _point_is_inside_polygon(
    point_x: float,
    point_y: float,
    polygon_coordinates: list[list[float]],
) -> bool:
    point_is_inside = False
    number_of_vertices = len(polygon_coordinates)

    for vertex_index in range(number_of_vertices):
        current_vertex_x, current_vertex_y = polygon_coordinates[vertex_index]
        next_vertex_x, next_vertex_y = polygon_coordinates[
            (vertex_index + 1) % number_of_vertices
        ]

        if (current_vertex_y > point_y) != (next_vertex_y > point_y):
            x_intersection = (
                (next_vertex_x - current_vertex_x)
                * (point_y - current_vertex_y)
                / (next_vertex_y - current_vertex_y)
                + current_vertex_x
            )
            if point_x < x_intersection:
                point_is_inside = not point_is_inside

    return point_is_inside


def _point_is_inside_munich(
    point_x: float,
    point_y: float,
    munich_geojson: dict,
) -> bool:
    for feature in munich_geojson["features"]:
        geometry = feature["geometry"]
        if geometry["type"] == "Polygon":
            polygons = [geometry["coordinates"]]
        elif geometry["type"] == "MultiPolygon":
            polygons = geometry["coordinates"]
        else:
            continue

        for polygon in polygons:
            for polygon_ring in polygon:
                if _point_is_inside_polygon(
                    point_x,
                    point_y,
                    polygon_ring,
                ):
                    return True

    return False


def create_munich_stops_csv(
    stops_bytes: bytes,
    geojson_path: str | Path = "data/static/munich.geojson",
) -> bytes:
    """Create the Munich stop list from GTFS stops and the city boundary."""
    stops_df = pd.read_csv(BytesIO(stops_bytes))
    with Path(geojson_path).open(encoding="utf-8") as file:
        munich_map = json.load(file)

    stops_df[["utm_x", "utm_y"]] = stops_df.apply(
        lambda row: wgs84_to_utm32(row["stop_lat"], row["stop_lon"]),
        axis=1,
        result_type="expand",
    )
    stops_df["inside_munich"] = stops_df.apply(
        lambda row: _point_is_inside_munich(
            row["utm_x"],
            row["utm_y"],
            munich_map,
        ),
        axis=1,
    )

    return stops_df[stops_df["inside_munich"]].to_csv().encode("utf-8")


def find_changed_munich_stops(
    stops_bytes: bytes,
    output_path: Path = Path("data/static/munich_stops.csv"),
    geojson_path: str | Path = "data/static/munich.geojson",
) -> bool:
    """Return whether the generated Munich stop list differs locally."""
    generated = create_munich_stops_csv(stops_bytes, geojson_path)
    return not output_path.exists() or output_path.read_bytes() != generated


def update_munich_stops(
    stops_bytes: bytes,
    output_path: Path = Path("data/static/munich_stops.csv"),
    geojson_path: str | Path = "data/static/munich.geojson",
) -> bool:
    """Write the Munich stop list when its generated content changed."""
    generated = create_munich_stops_csv(stops_bytes, geojson_path)
    if output_path.exists() and output_path.read_bytes() == generated:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(generated)
    return True
