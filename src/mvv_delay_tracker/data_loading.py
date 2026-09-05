import requests
import pandas as pd
from datetime import datetime
from google.transit import gtfs_realtime_pb2


GTFS_REALTIME_URL = "https://realtime.gtfs.de/realtime-free.pb"

MUNICH_AGENCIES = ["100", "191", "364"]


def load_gtfs_realtime_feed(
    url=GTFS_REALTIME_URL,
):
    """
    Download and parse the current GTFS-RT feed.

    Parameters
    ----------
    url : str
        URL of the GTFS-RT feed.

    Returns
    -------
    FeedMessage
        Parsed GTFS-RT feed.
    """

    response = requests.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)

    return feed


def preprocess_gtfs(
    data_dir,
    munich_agencies=MUNICH_AGENCIES,
):
    """
    Preprocess static GTFS data for the selected agencies.

    Parameters
    ----------
    data_dir : str
        Directory containing routes.txt, trips.txt and stops.txt.

    munich_agencies : list[str]
        Agency IDs to include.

    Returns
    -------
    trip_lines : dict
        Mapping from trip_id to line name.

    stop_names : dict
        Mapping from stop_id to stop name.
    """

    routes_df = pd.read_csv(
        f"{data_dir}/routes.txt"
    )

    trips_df = pd.read_csv(
        f"{data_dir}/trips.txt"
    )

    stops_df = pd.read_csv(
        f"{data_dir}/stops.txt"
    )

    # Make IDs consistent across all datasets
    routes_df["route_id"] = routes_df["route_id"].astype(str)
    routes_df["agency_id"] = routes_df["agency_id"].astype(str)

    trips_df["trip_id"] = trips_df["trip_id"].astype(str)
    trips_df["route_id"] = trips_df["route_id"].astype(str)

    stops_df["stop_id"] = stops_df["stop_id"].astype(str)

    # Select routes belonging to the selected agencies
    munich_routes = routes_df[
        routes_df["agency_id"].isin(munich_agencies)
    ]

    route_lines = (
        munich_routes
        .set_index("route_id")["route_short_name"]
        .to_dict()
    )

    # Select trips belonging to these routes
    munich_trips = trips_df[
        trips_df["route_id"].isin(route_lines)
    ]

    trip_lines = (
        munich_trips
        .set_index("trip_id")["route_id"]
        .map(route_lines)
        .to_dict()
    )

    # Map stop IDs to stop names
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
):
    """
    Parse GTFS-RT trip updates into a pandas DataFrame.

    Parameters
    ----------
    feed : FeedMessage
        Parsed GTFS-RT feed.

    stop_names : dict
        Mapping from stop IDs to stop names.

    trip_lines : dict
        Mapping from trip IDs to line names.

    Returns
    -------
    pandas.DataFrame
        DataFrame containing trip, line, stop,
        arrival, departure and delay information.
    """

    rows = []

    for entity in feed.entity:

        if not entity.HasField("trip_update"):
            continue

        trip = entity.trip_update.trip

        # Get line for this trip
        line = trip_lines.get(
            str(trip.trip_id)
        )

        # Ignore trips that are not part
        # of the selected agencies
        if line is None:
            continue

        for stop in entity.trip_update.stop_time_update:

            row = {
                "trip_id": trip.trip_id,
                "start_date": trip.start_date,
                "line": line,
                "stop_id": str(stop.stop_id),
                "stop_name": stop_names.get(
                    str(stop.stop_id)
                ),
                "stop_sequence": stop.stop_sequence,
            }

            if stop.HasField("departure"):

                row["departure_time"] = (
                    datetime.fromtimestamp(
                        stop.departure.time
                    )
                )

                row["departure_delay"] = (
                    stop.departure.delay
                )

            if stop.HasField("arrival"):

                row["arrival_time"] = (
                    datetime.fromtimestamp(
                        stop.arrival.time
                    )
                )

                row["arrival_delay"] = (
                    stop.arrival.delay
                )

            rows.append(row)

    return pd.DataFrame(rows)


def load_new_data(
    data_dir="data",
):
    """
    Load and process the current MVV real-time data.

    Parameters
    ----------
    data_dir : str
        Directory containing the static GTFS files.

    Returns
    -------
    pandas.DataFrame
        Current MVV real-time observations.
    """

    feed = load_gtfs_realtime_feed()

    trip_lines, stop_names = preprocess_gtfs(
        data_dir=data_dir,
    )

    realtime_df = parse_trip_updates(
        feed=feed,
        stop_names=stop_names,
        trip_lines=trip_lines,
    )

    return realtime_df