import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from google.transit import gtfs_realtime_pb2


GTFS_REALTIME_URL = "https://realtime.gtfs.de/realtime-free.pb"
LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")


def _epoch_to_local_datetime(timestamp: int) -> datetime:
    """Convert a GTFS-RT UTC epoch timestamp to German local time."""
    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)


def compute_is_prediction(delay_df: pd.DataFrame) -> pd.Series:
    """
    A stop visit is a prediction until it has been observed after
    its scheduled arrival. SKIPPED stop visits are never predictions.
    """
    row_count = len(delay_df)

    if "observation_timestamp" in delay_df.columns:
        observation_timestamp = pd.to_datetime(
            delay_df["observation_timestamp"], errors="coerce"
        )
    else:
        observation_timestamp = pd.Series(pd.NaT, index=delay_df.index)

    if "arrival_time" in delay_df.columns:
        arrival_time = pd.to_datetime(
            delay_df["arrival_time"], errors="coerce"
        )
    else:
        arrival_time = pd.Series(pd.NaT, index=delay_df.index)

    if "stop_schedule_relationship" in delay_df.columns:
        skipped_mask = delay_df["stop_schedule_relationship"] == "SKIPPED"
    else:
        skipped_mask = pd.Series(False, index=delay_df.index)

    observed_after_arrival = observation_timestamp > arrival_time

    return ~(skipped_mask | observed_after_arrival) if row_count else pd.Series(
        dtype=bool, index=delay_df.index
    )


def load_gtfs_realtime_feed(
    url: str = GTFS_REALTIME_URL,
) -> gtfs_realtime_pb2.FeedMessage:
    """
    Download and parse the current GTFS-RT feed.
    """

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)

    return feed


def preprocess_gtfs(
    data_dir: str,
) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """
    Load static GTFS metadata and Munich stop names.

    Parameters
    ----------
    data_dir : str
        Directory containing routes.txt, trips.txt and munich_stops.csv.

    Returns
    -------
    trip_info : dict
        Mapping from trip_id to line and agency information.

    stop_names : dict
        Mapping from GTFS stop_id to stop name.
    """

    static_data_directory = Path(data_dir) / "static"

    routes_df = pd.read_csv(
        static_data_directory / "routes.txt",
        dtype={
            "route_id": str,
            "agency_id": str,
        },
    )

    agency_df = pd.read_csv(
        static_data_directory / "agency.txt",
        dtype={"agency_id": str},
    )
    agency_names = (
        agency_df
        .set_index("agency_id")["agency_name"]
        .to_dict()
    )

    trips_df = pd.read_csv(
        static_data_directory / "trips.txt",
        dtype={
            "trip_id": str,
            "route_id": str,
        },
    )

    stops_df = pd.read_csv(
        static_data_directory / "munich_stops.csv",
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
            "agency_name": agency_names.get(
                route_info[route_id]["agency_id"]
            ),
        }

    stop_names = (
        stops_df
        .set_index("stop_id")["stop_name"]
        .to_dict()
    )

    return trip_info, stop_names


def parse_trip_updates(
    feed: gtfs_realtime_pb2.FeedMessage,
    stop_names: dict[str, str],
    trip_info: dict[str, dict[str, str]],
    observation_timestamp: datetime,
) -> pd.DataFrame:
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

        trip_schedule_relationship = (
            gtfs_realtime_pb2.TripDescriptor.ScheduleRelationship.Name(
                trip.schedule_relationship
            )
        )

        for stop in entity.trip_update.stop_time_update:

            stop_id = str(stop.stop_id)

            if stop_id not in stop_names:
                continue

            stop_schedule_relationship = (
                gtfs_realtime_pb2.TripUpdate.StopTimeUpdate
                .ScheduleRelationship.Name(
                    stop.schedule_relationship
                )
            )

            row = {
                "observation_timestamp": observation_timestamp,
                "trip_id": trip_id,
                "start_date": trip.start_date,
                "trip_schedule_relationship":
                    trip_schedule_relationship,
                "stop_schedule_relationship":
                    stop_schedule_relationship,
                "line": info["line"],
                "agency_id": info["agency_id"],
                "agency_name": info["agency_name"],
                "stop_id": stop_id,
                "stop_name": stop_names[stop_id],
                "stop_sequence": stop.stop_sequence,
            }

            if stop.HasField("departure"):
                row["departure_time"] = _epoch_to_local_datetime(
                    stop.departure.time
                )
                row["departure_delay"] = stop.departure.delay

            if stop.HasField("arrival"):
                row["arrival_time"] = _epoch_to_local_datetime(
                    stop.arrival.time
                )
                row["arrival_delay"] = stop.arrival.delay

            rows.append(row)

    realtime_df = pd.DataFrame(rows)
    realtime_df["is_prediction"] = compute_is_prediction(realtime_df)

    return realtime_df


def load_new_data(
    data_dir: str = "data",
) -> pd.DataFrame:
    """
    Load and process the current MVV real-time data.
    """

    observation_timestamp = datetime.now(LOCAL_TIMEZONE).replace(
        tzinfo=None
    )

    feed = load_gtfs_realtime_feed()

    trip_info, stop_names = preprocess_gtfs(
        data_dir=data_dir,
    )

    realtime_df = parse_trip_updates(
        feed=feed,
        stop_names=stop_names,
        trip_info=trip_info,
        observation_timestamp=observation_timestamp,
    )

    return realtime_df