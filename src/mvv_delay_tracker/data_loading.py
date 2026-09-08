import json
import math
import requests
import pandas as pd
from datetime import datetime
from google.transit import gtfs_realtime_pb2

GTFS_REALTIME_URL = "https://realtime.gtfs.de/realtime-free.pb"



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
):
    """
    Preprocess static GTFS data and filter stops geographically
    to the Munich boundary.

    Parameters
    ----------
    data_dir : str
        Directory containing routes.txt, trips.txt and munich_stops.csv.

    munich_geojson_path : str
        Path to the GeoJSON file containing the Munich boundary.

    Returns
    -------
    trip_lines : dict
        Mapping from trip_id to line name.

    stop_names : dict
        Mapping from stop_id to stop name.
    """

    routes_df = pd.read_csv(
        f"{data_dir}/routes.txt",
        dtype={
            "route_id": str,
        },
    )

    trips_df = pd.read_csv(
        f"{data_dir}/trips.txt",
        dtype={
            "trip_id": str,
            "route_id": str,
        },
    )

    stops_df = pd.read_csv(
        f"{data_dir}/munich_stops.csv",
        dtype={
            "stop_id": str,
        },
    )

    route_lines = (
        routes_df
        .set_index("route_id")["route_short_name"]
        .to_dict()
    )

    trip_lines = (
        trips_df
        .set_index("trip_id")["route_id"]
        .map(route_lines)
        .dropna()
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
    munich_geojson_path="munich.geojson",
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