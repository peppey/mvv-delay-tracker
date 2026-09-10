from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import pandas as pd

from mvv_delay_tracker.analysis.geographic import wgs84_to_utm32


def point_is_inside_polygon(
    point_x: float,
    point_y: float,
    polygon_coordinates: list[list[float]],
) -> bool:
    """Return whether a point is inside a polygon ring."""

    point_is_inside = False
    number_of_vertices = len(polygon_coordinates)

    for vertex_index in range(number_of_vertices):
        current_vertex_x, current_vertex_y = (
            polygon_coordinates[vertex_index]
        )
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


def point_is_inside_munich(
    point_x: float,
    point_y: float,
    munich_geojson: dict[str, Any],
) -> bool:
    """Return whether a projected point is inside Munich."""

    for feature in munich_geojson["features"]:
        geometry = feature["geometry"]
        geometry_type = geometry["type"]
        polygons = (
            [geometry["coordinates"]]
            if geometry_type == "Polygon"
            else geometry["coordinates"]
            if geometry_type == "MultiPolygon"
            else []
        )

        for polygon in polygons:
            for polygon_ring in polygon:
                if point_is_inside_polygon(
                    point_x,
                    point_y,
                    polygon_ring,
                ):
                    return True

    return False


def create_munich_stop_list(
    stops_content: bytes,
    munich_geojson_path: str = "data/static/munich.geojson",
) -> pd.DataFrame:
    """Create the Munich stop list from in-memory GTFS stops data."""

    stops_df = pd.read_csv(BytesIO(stops_content), dtype={"stop_id": str})
    with open(munich_geojson_path, encoding="utf-8") as geojson_file:
        munich_map = json.load(geojson_file)

    projected_coordinates = stops_df.apply(
        lambda row: wgs84_to_utm32(
            row["stop_lat"],
            row["stop_lon"],
        ),
        axis=1,
    )
    stops_df["utm_x"], stops_df["utm_y"] = zip(*projected_coordinates)
    stops_df["inside_munich"] = stops_df.apply(
        lambda row: point_is_inside_munich(
            row["utm_x"],
            row["utm_y"],
            munich_map,
        ),
        axis=1,
    )

    return stops_df[stops_df["inside_munich"]].copy()
