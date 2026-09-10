import requests
import pandas as pd
from datetime import datetime
import json
from pathlib import Path
from google.transit import gtfs_realtime_pb2


GTFS_REALTIME_URL = "https://realtime.gtfs.de/realtime-free.pb"


def load_trip_info_versions(
    path: str = "data/static/trip_info.json",
) -> dict[str, object]:
    """Load timestamped static trip metadata."""
    with open(path, encoding="utf-8") as file:
        document = json.load(file)
    for version in document.get("versions", {}).values():
        version["_trip_index"] = {
            trip_id: index
            for index, trip_id in enumerate(version["trips"]["ids"])
        }
    return document


def create_trip_info(
    routes_path: str = "data/static/routes.txt",
    trips_path: str = "data/static/trips.txt",
) -> dict[str, dict[str, str]]:
    """Create a legacy flat trip-to-line mapping from GTFS text files."""
    routes_df = pd.read_csv(
        routes_path,
        dtype={"route_id": str},
        usecols=["route_id", "route_short_name"],
    )
    trips_df = pd.read_csv(
        trips_path,
        dtype={"trip_id": str, "route_id": str},
        usecols=["trip_id", "route_id"],
    )
    route_names = routes_df.set_index("route_id")["route_short_name"]
    return {
        row["trip_id"]: {"line": route_names[row["route_id"]]}
        for row in trips_df[
            trips_df["route_id"].isin(route_names.index)
        ].to_dict("records")
    }


def _service_is_active(
    service: dict[str, object],
    start_date: str,
) -> bool:
    """Return whether a GTFS service operates on ``start_date``."""
    if start_date in service["added_dates"]:
        return True
    if start_date in service["removed_dates"]:
        return False
    if service["start_date"] is None or service["end_date"] is None:
        return False
    if not service["start_date"] <= start_date <= service["end_date"]:
        return False

    weekday = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ][datetime.strptime(start_date, "%Y%m%d").weekday()]
    return weekday in service["weekdays"]


def _resolve_trip_info(
    trip_id: str,
    start_date: str,
    trip_info_versions: dict[str, object],
) -> dict[str, str] | None:
    """Resolve a trip from newest to oldest compatible GTFS version."""
    versions = trip_info_versions.get("versions", {})
    for timestamp in sorted(versions, reverse=True):
        version = versions[timestamp]
        trip_index = version["_trip_index"].get(trip_id)
        if trip_index is None:
            continue
        agency = version["agencies"][
            version["trips"]["agency_index"][trip_index]
        ]
        service_id = version["service_ids"][
            version["trips"]["service_index"][trip_index]
        ]
        service = version["services"].get(service_id)
        if service is not None and _service_is_active(service, start_date):
            resolved = {
                "line": version["lines"][
                    version["trips"]["line_index"][trip_index]
                ],
                "agency_id": agency["agency_id"],
                "agency_name": agency["agency_name"],
                "service_id": service_id,
            }
            resolved["planned_departure_days"] = service["weekdays"]
            return resolved
    return None


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
    Load timestamped static GTFS metadata and Munich stop names.

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
    trip_info_path = static_data_directory / "trip_info.json"
    if trip_info_path.exists():
        trip_info_versions = load_trip_info_versions(str(trip_info_path))
    else:
        routes_df = pd.read_csv(
            static_data_directory / "routes.txt",
            dtype={"route_id": str, "agency_id": str},
        )
        trips_df = pd.read_csv(
            static_data_directory / "trips.txt",
            dtype={"trip_id": str, "route_id": str},
        )
        route_info = (
            routes_df[
                ["route_id", "route_short_name", "agency_id"]
            ]
            .set_index("route_id")
            .to_dict("index")
        )
        trip_info_versions = {
            trip["trip_id"]: {
                "line": route_info[trip["route_id"]]["route_short_name"],
                "agency_id": route_info[trip["route_id"]]["agency_id"],
            }
            for trip in trips_df.to_dict("records")
            if trip["route_id"] in route_info
        }

    stops_df = pd.read_csv(
        static_data_directory / "munich_stops.csv",
        dtype={
            "stop_id": str,
        },
    )

    stop_names = (
        stops_df
        .set_index("stop_id")["stop_name"]
        .to_dict()
    )

    return trip_info_versions, stop_names


def parse_trip_updates(
    feed: gtfs_realtime_pb2.FeedMessage,
    stop_names: dict[str, str],
    trip_info: dict[str, object],
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

        if "versions" in trip_info:
            info = _resolve_trip_info(
                trip_id,
                trip.start_date,
                trip_info,
            )
        else:
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
                "agency_name": info.get("agency_name"),
                "planned_departure_days": info.get(
                    "planned_departure_days"
                ),
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
    data_dir: str = "data",
) -> pd.DataFrame:
    """
    Load and process the current MVV real-time data.
    """

    observation_timestamp = datetime.now()

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