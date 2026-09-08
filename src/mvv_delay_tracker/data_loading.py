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
    trip_info : dict
        Mapping from trip_id to line and agency information.

    stop_names : dict
        Mapping from stop_id to stop name.
    """

    routes_df = pd.read_csv(
        f"{data_dir}/routes.txt",
        dtype={
            "route_id": str,
            "agency_id": str,
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

    route_info = (
        routes_df[
            [
                "route_id",
                "route_short_name",
                "agency_id",
            ]
        ]
        .set_index("route_id")
        .to_dict("index")
    )

    trip_info = {}

    for _, trip in trips_df.iterrows():
        route_id = trip["route_id"]

        if route_id not in route_info:
            continue

        trip_info[trip["trip_id"]] = {
            "line": route_info[route_id]["route_short_name"],
            "agency_id": route_info[route_id]["agency_id"],
        }

    stop_names = (
        stops_df
        .set_index("stop_id")["stop_name"]
        .to_dict()
    )

    return trip_info, stop_names


def parse_trip_updates(
    feed,
    stop_names,
    trip_info,
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

        trip_id = str(trip.trip_id)

        info = trip_info.get(trip_id)

        if info is None:
            continue

        for stop in entity.trip_update.stop_time_update:

            stop_id = str(stop.stop_id)

            if stop_id not in stop_names:
                continue

            row = {
                "observation_timestamp": observation_timestamp,
                "trip_id": trip_id,
                "start_date": trip.start_date,
                "line": info["line"],
                "agency_id": info["agency_id"],
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

    trip_info, stop_names = preprocess_gtfs(
        data_dir=data_dir,
        munich_geojson_path=munich_geojson_path,
    )

    realtime_df = parse_trip_updates(
        feed=feed,
        stop_names=stop_names,
        trip_info=trip_info,
        observation_timestamp=observation_timestamp,
    )

    return realtime_df