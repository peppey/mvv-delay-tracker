from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pandas as pd

from mvv_delay_tracker.analysis.geographic import wgs84_to_utm32

# The nationwide GTFS feed reuses route_short_name values across many
# agencies (e.g. "19" or "S1" also exist far outside Munich), so matching
# munich_lines.csv by name alone can pull in unrelated routes - including
# international/cross-border ones - whose full stop list then gets included.
# Restricting matches to the actual Munich operator (via mode) prevents that.
MODE_TO_AGENCY_AND_ROUTE_TYPES: dict[str, tuple[str, set[str]]] = {
    "U-Bahn": ("Stadtwerke München", {"1"}),
    "Tram": ("Stadtwerke München", {"0"}),
    "Bus": ("Stadtwerke München", {"3"}),
    "S-Bahn": ("DB S-Bahn München", {"3"}),
}


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


def filter_munich_routes(
    routes_df: pd.DataFrame,
    agency_df: pd.DataFrame,
    lines_path: str | Path = "data/static/munich_lines.csv",
) -> pd.DataFrame:
    """Return only the routes.txt rows that are genuine Munich lines.

    route_short_name values are reused by unrelated agencies nationwide, so a
    name match against munich_lines.csv only counts if the route's actual
    agency and route_type also match the line's configured mode.
    """
    lines = pd.read_csv(lines_path, dtype=str)
    expected_agency_and_types_by_line = {
        line.strip(): MODE_TO_AGENCY_AND_ROUTE_TYPES[mode.strip()]
        for line, mode in zip(lines["line"], lines["mode"])
    }
    munich_agency_names = {
        agency_name
        for agency_name, _ in expected_agency_and_types_by_line.values()
    }

    route_names = routes_df[
        ["route_id", "route_short_name", "route_long_name", "agency_id", "route_type"]
    ].fillna("")
    route_names["route_short_name"] = (
        route_names["route_short_name"].str.strip()
    )
    route_names["route_long_name"] = (
        route_names["route_long_name"].str.strip()
    )
    route_names = route_names.merge(
        agency_df[["agency_id", "agency_name"]], on="agency_id", how="left"
    )
    route_names["agency_name"] = route_names["agency_name"].fillna("")

    def _matches_configured_line(row: pd.Series) -> bool:
        expected = expected_agency_and_types_by_line.get(
            row["route_short_name"]
        )
        if expected is None:
            return False
        expected_agency_name, expected_route_types = expected
        return (
            row["agency_name"] == expected_agency_name
            and row["route_type"] in expected_route_types
        )

    route_names["is_configured"] = route_names.apply(
        _matches_configured_line, axis=1
    )
    route_names["is_sev"] = route_names["agency_name"].isin(
        munich_agency_names
    ) & (
        route_names["route_short_name"].str.contains(
            "SEV", case=False, regex=False
        )
        | route_names["route_long_name"].str.contains(
            "SEV", case=False, regex=False
        )
    )
    return route_names.loc[
        route_names["is_configured"] | route_names["is_sev"]
    ]


def create_munich_stops_csv(
    stops_bytes: bytes,
    geojson_path: str | Path = "data/static/munich.geojson",
    routes_bytes: bytes | None = None,
    trips_bytes: bytes | None = None,
    stop_times_bytes: bytes | None = None,
    agency_bytes: bytes | None = None,
    lines_path: str | Path = "data/static/munich_lines.csv",
) -> bytes:
    """Create the stop list for Munich lines and their complete routes."""
    stops_df = pd.read_csv(BytesIO(stops_bytes), dtype={"stop_id": str})
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

    if all(
        value is not None
        for value in (routes_bytes, trips_bytes, stop_times_bytes, agency_bytes)
    ):
        routes = pd.read_csv(BytesIO(routes_bytes), dtype=str)
        trips = pd.read_csv(BytesIO(trips_bytes), dtype=str)
        stop_times = pd.read_csv(
            BytesIO(stop_times_bytes),
            usecols=["trip_id", "stop_id"],
            dtype=str,
        )
        agency = pd.read_csv(BytesIO(agency_bytes), dtype=str)
        route_names = filter_munich_routes(routes, agency, lines_path)

        route_stops = (
            stop_times
            .merge(trips[["trip_id", "route_id"]], on="trip_id")
            .merge(route_names[["route_id"]], on="route_id")
            .merge(
                stops_df[["stop_id", "inside_munich"]],
                on="stop_id",
                how="left",
            )
        )
        routes_with_munich_stop = set(
            route_stops.loc[route_stops["inside_munich"], "route_id"]
        )
        included_stop_ids = set(
            route_stops.loc[
                route_stops["route_id"].isin(routes_with_munich_stop),
                "stop_id",
            ]
        )
        result = stops_df[stops_df["stop_id"].isin(included_stop_ids)]
    else:
        result = stops_df[stops_df["inside_munich"]]

    return result.to_csv().encode("utf-8")


def find_changed_munich_stops(
    stops_bytes: bytes,
    output_path: Path = Path("data/static/munich_stops.csv"),
    geojson_path: str | Path = "data/static/munich.geojson",
    routes_bytes: bytes | None = None,
    trips_bytes: bytes | None = None,
    stop_times_bytes: bytes | None = None,
    agency_bytes: bytes | None = None,
    lines_path: str | Path = "data/static/munich_lines.csv",
) -> bool:
    """Return whether the generated Munich stop list differs locally."""
    generated = create_munich_stops_csv(
        stops_bytes,
        geojson_path,
        routes_bytes,
        trips_bytes,
        stop_times_bytes,
        agency_bytes,
        lines_path,
    )
    return not output_path.exists() or output_path.read_bytes() != generated


def update_munich_stops(
    stops_bytes: bytes,
    output_path: Path = Path("data/static/munich_stops.csv"),
    geojson_path: str | Path = "data/static/munich.geojson",
    routes_bytes: bytes | None = None,
    trips_bytes: bytes | None = None,
    stop_times_bytes: bytes | None = None,
    agency_bytes: bytes | None = None,
    lines_path: str | Path = "data/static/munich_lines.csv",
) -> bool:
    """Write the Munich stop list when its generated content changed."""
    generated = create_munich_stops_csv(
        stops_bytes,
        geojson_path,
        routes_bytes,
        trips_bytes,
        stop_times_bytes,
        agency_bytes,
        lines_path,
    )
    if output_path.exists() and output_path.read_bytes() == generated:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(generated)
    return True
