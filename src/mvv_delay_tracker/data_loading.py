import json
import math
import requests
import pandas as pd
from datetime import datetime
from google.transit import gtfs_realtime_pb2

GTFS_REALTIME_URL = "https://realtime.gtfs.de/realtime-free.pb"

MUNICH_AGENCIES = ["100", "191", "364"]


def load_gtfs_realtime_feed(url=GTFS_REALTIME_URL):
    """
    Download and parse the current GTFS-RT feed.
    """

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)

    return feed


def preprocess_gtfs(
    data_dir,
    munich_geojson_path,
    munich_agencies=MUNICH_AGENCIES,
):
    """
    Preprocess static GTFS data for the selected Munich agencies
    and filter stops geographically to the Munich boundary.

    Parameters
    ----------
    data_dir : str
        Directory containing routes.txt, trips.txt and munich_stops.csv.

    munich_geojson_path : str
        Path to the GeoJSON file containing the Munich boundary.

    munich_agencies : list[str]
        Agency IDs to include.

    Returns
    -------
    trip_lines : dict
        Mapping from trip_id to line name.

    stop_names : dict
        Mapping from geographically valid stop_id to stop name.
    """

    routes_df = pd.read_csv(f"{data_dir}/routes.txt")
    trips_df = pd.read_csv(f"{data_dir}/trips.txt")
    stops_df = pd.read_csv(f"{data_dir}/munich_stops.csv")

    routes_df["route_id"] = routes_df["route_id"].astype(str)
    routes_df["agency_id"] = routes_df["agency_id"].astype(str)

    trips_df["trip_id"] = trips_df["trip_id"].astype(str)
    trips_df["route_id"] = trips_df["route_id"].astype(str)

    stops_df["stop_id"] = stops_df["stop_id"].astype(str)

    munich_routes = routes_df[
        routes_df["agency_id"].isin(munich_agencies)
    ]

    route_lines = (
        munich_routes
        .set_index("route_id")["route_short_name"]
        .to_dict()
    )

    munich_trips = trips_df[
        trips_df["route_id"].isin(route_lines)
    ]

    trip_lines = (
        munich_trips
        .set_index("trip_id")["route_id"]
        .map(route_lines)
        .to_dict()
    )

    stop_names = (
        stops_df
        .set_index("stop_id")["stop_name"]
        .to_dict()
    )

    return trip_lines, stop_names


def parse_trip_updates(
    feed,
    stop_names,
    trip_lines,
    observation_timestamp,
):
    """
    Parse GTFS-RT trip updates into a pandas DataFrame.
    """

    rows = []

    for entity in feed.entity:

        if not entity.HasField("trip_update"):
            continue

        trip = entity.trip_update.trip

        line = trip_lines.get(str(trip.trip_id))

        if line is None:
            continue

        for stop in entity.trip_update.stop_time_update:

            stop_id = str(stop.stop_id)

            if stop_id not in stop_names:
                continue

            row = {
                "observation_timestamp": observation_timestamp,
                "trip_id": trip.trip_id,
                "start_date": trip.start_date,
                "line": line,
                "stop_id": stop_id,
                "stop_name": stop_names[stop_id],
                "stop_sequence": stop.stop_sequence,
            }

            if stop.HasField("departure"):
                row["departure_time"] = datetime.fromtimestamp(
                    stop.departure.time
                )
                row["departure_delay"] = stop.departure.delay

            if stop.HasField("arrival"):
                row["arrival_time"] = datetime.fromtimestamp(
                    stop.arrival.time
                )
                row["arrival_delay"] = stop.arrival.delay

            rows.append(row)

    return pd.DataFrame(rows)


def load_new_data(
    data_dir="data",
    munich_geojson_path="data/munich.geojson",
):
    """
    Load and process the current MVV real-time data.
    """

    observation_timestamp = datetime.now()

    feed = load_gtfs_realtime_feed()

    trip_lines, stop_names = preprocess_gtfs(
        data_dir=data_dir,
        munich_geojson_path=munich_geojson_path,
    )

    realtime_df = parse_trip_updates(
        feed=feed,
        stop_names=stop_names,
        trip_lines=trip_lines,
        observation_timestamp=observation_timestamp,
    )

    return realtime_df