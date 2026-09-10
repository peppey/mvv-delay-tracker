import pandas as pd
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from mvv_delay_tracker.realtime.data_loading import (
    create_trip_info,
    _resolve_trip_info,
    load_gtfs_realtime_feed,
    preprocess_gtfs,
    parse_trip_updates,
    load_new_data,
)


@pytest.fixture
def sample_stop_names():
    return {
        "1001": "Marienplatz",
        "1002": "Karlsplatz",
    }


@pytest.fixture
def sample_trip_info():
    return {
        "123": {
            "line": "S1",
            "agency_id": "191",
        },
        "456": {
            "line": "S8",
            "agency_id": "364",
        },
    }


@pytest.fixture
def observation_timestamp():
    return datetime(2026, 9, 9, 10, 0, 0)


def test_load_gtfs_realtime_feed_success():
    response = Mock()
    response.content = b""
    response.raise_for_status = Mock()

    with patch(
        "mvv_delay_tracker.realtime.data_loading.requests.get",
        return_value=response,
    ) as mock_get:

        feed = load_gtfs_realtime_feed("http://test-url")

    mock_get.assert_called_once_with(
        "http://test-url",
        timeout=30,
    )

    response.raise_for_status.assert_called_once()

    assert feed is not None


def test_load_gtfs_realtime_feed_http_error():
    response = Mock()
    response.raise_for_status.side_effect = Exception("HTTP error")

    with patch(
        "mvv_delay_tracker.realtime.data_loading.requests.get",
        return_value=response,
    ):

        with pytest.raises(Exception, match="HTTP error"):
            load_gtfs_realtime_feed("http://test-url")


def test_preprocess_gtfs_returns_line_and_agency(tmp_path):
    routes = pd.DataFrame({
        "route_id": [1, 2, 3],
        "agency_id": [191, 364, 999],
        "route_short_name": ["S1", "S8", "X1"],
    })

    trips = pd.DataFrame({
        "trip_id": [101, 102, 103],
        "route_id": [1, 2, 3],
    })

    stops = pd.DataFrame({
        "stop_id": [1001, 1002],
        "stop_name": ["Marienplatz", "Karlsplatz"],
    })

    static_dir = tmp_path / "static"
    static_dir.mkdir()

    routes.to_csv(static_dir / "routes.txt", index=False)
    trips.to_csv(static_dir / "trips.txt", index=False)
    stops.to_csv(static_dir / "munich_stops.csv", index=False)

    trip_info, stop_names = preprocess_gtfs(
        data_dir=str(tmp_path),
    )

    assert trip_info == {
        "101": {
            "line": "S1",
            "agency_id": "191",
        },
        "102": {
            "line": "S8",
            "agency_id": "364",
        },
        "103": {
            "line": "X1",
            "agency_id": "999",
        },
    }

    assert stop_names == {
        "1001": "Marienplatz",
        "1002": "Karlsplatz",
    }


def test_create_trip_info_includes_all_routes_without_stops(tmp_path):
    routes = pd.DataFrame({
        "route_id": ["munich", "outside"],
        "route_short_name": ["S1", "X1"],
    })
    trips = pd.DataFrame({
        "trip_id": ["trip_munich", "trip_outside"],
        "route_id": ["munich", "outside"],
    })

    routes_path = tmp_path / "routes.txt"
    trips_path = tmp_path / "trips.txt"
    routes.to_csv(routes_path, index=False)
    trips.to_csv(trips_path, index=False)

    assert create_trip_info(
        routes_path=str(routes_path),
        trips_path=str(trips_path),
    ) == {
        "trip_munich": {"line": "S1"},
        "trip_outside": {"line": "X1"},
    }


def test_resolve_trip_info_uses_older_active_version():
    trip_info_versions = {
        "versions": {
            "2026-09-10T00:00:00+02:00": {
                "trips": {
                    "ids": [],
                    "line_index": [],
                    "agency_index": [],
                    "service_index": [],
                },
                "lines": [],
                "agencies": [],
                "service_ids": [],
                "services": {},
            },
            "2026-09-05T12:00:00+02:00": {
                "trips": {
                    "ids": ["trip-1"],
                    "line_index": [0],
                    "agency_index": [0],
                    "service_index": [0],
                },
                "lines": ["S1"],
                "agencies": [
                    {"agency_id": "a1", "agency_name": "Agency One"}
                ],
                "service_ids": ["service-1"],
                "services": {
                    "service-1": {
                        "start_date": "20260901",
                        "end_date": "20260930",
                        "weekdays": ["thursday"],
                        "added_dates": [],
                        "removed_dates": [],
                    }
                },
            },
        }
    }
    for version in trip_info_versions["versions"].values():
        version["_trip_index"] = {
            trip_id: index
            for index, trip_id in enumerate(version["trips"]["ids"])
        }

    assert _resolve_trip_info(
        "trip-1",
        "20260910",
        trip_info_versions,
    ) == {
        "line": "S1",
        "agency_id": "a1",
        "agency_name": "Agency One",
        "service_id": "service-1",
        "planned_departure_days": ["thursday"],
    }


def test_preprocess_gtfs_converts_ids_to_strings(tmp_path):
    routes = pd.DataFrame({
        "route_id": [123],
        "agency_id": [191],
        "route_short_name": ["S1"],
    })

    trips = pd.DataFrame({
        "trip_id": [456],
        "route_id": [123],
    })

    stops = pd.DataFrame({
        "stop_id": [789],
        "stop_name": ["Test Stop"],
    })

    static_dir = tmp_path / "static"
    static_dir.mkdir()

    routes.to_csv(static_dir / "routes.txt", index=False)
    trips.to_csv(static_dir / "trips.txt", index=False)
    stops.to_csv(static_dir / "munich_stops.csv", index=False)

    trip_info, stop_names = preprocess_gtfs(
        data_dir=str(tmp_path),
    )

    assert trip_info == {
        "456": {
            "line": "S1",
            "agency_id": "191",
        }
    }

    assert stop_names == {
        "789": "Test Stop",
    }


def test_preprocess_gtfs_keeps_all_agencies(tmp_path):
    routes = pd.DataFrame({
        "route_id": ["munich", "outside"],
        "agency_id": ["191", "999"],
        "route_short_name": ["S1", "X1"],
    })

    trips = pd.DataFrame({
        "trip_id": ["trip_munich", "trip_outside"],
        "route_id": ["munich", "outside"],
    })

    stops = pd.DataFrame({
        "stop_id": ["1"],
        "stop_name": ["Marienplatz"],
    })

    static_dir = tmp_path / "static"
    static_dir.mkdir()

    routes.to_csv(static_dir / "routes.txt", index=False)
    trips.to_csv(static_dir / "trips.txt", index=False)
    stops.to_csv(static_dir / "munich_stops.csv", index=False)

    trip_info, _ = preprocess_gtfs(
        data_dir=str(tmp_path),
    )

    assert trip_info["trip_munich"] == {
        "line": "S1",
        "agency_id": "191",
    }

    assert trip_info["trip_outside"] == {
        "line": "X1",
        "agency_id": "999",
    }


def create_trip_update_feed(
    trip_id="123",
    stop_id="1001",
    departure_time=1757412000,
    departure_delay=60,
):
    from google.transit import gtfs_realtime_pb2

    feed = gtfs_realtime_pb2.FeedMessage()

    entity = feed.entity.add()
    entity.id = "entity_1"

    trip_update = entity.trip_update

    trip_update.trip.trip_id = trip_id
    trip_update.trip.start_date = "20260909"

    stop_update = trip_update.stop_time_update.add()

    stop_update.stop_id = stop_id
    stop_update.stop_sequence = 1

    stop_update.departure.time = departure_time
    stop_update.departure.delay = departure_delay

    return feed


def test_parse_trip_updates_parses_valid_trip(
    sample_stop_names,
    sample_trip_info,
    observation_timestamp,
):
    feed = create_trip_update_feed()

    df = parse_trip_updates(
        feed=feed,
        stop_names=sample_stop_names,
        trip_info=sample_trip_info,
        observation_timestamp=observation_timestamp,
    )

    assert len(df) == 1

    row = df.iloc[0]

    assert row["trip_id"] == "123"
    assert row["start_date"] == "20260909"
    assert row["line"] == "S1"
    assert row["agency_id"] == "191"
    assert row["stop_id"] == "1001"
    assert row["stop_name"] == "Marienplatz"
    assert row["stop_sequence"] == 1
    assert row["departure_delay"] == 60
    assert row["observation_timestamp"] == observation_timestamp


def test_parse_trip_updates_ignores_unknown_trip(
    sample_stop_names,
    observation_timestamp,
):
    feed = create_trip_update_feed(
        trip_id="unknown_trip",
    )

    df = parse_trip_updates(
        feed=feed,
        stop_names=sample_stop_names,
        trip_info={},
        observation_timestamp=observation_timestamp,
    )

    assert df.empty


def test_parse_trip_updates_ignores_unknown_stop(
    sample_trip_info,
    observation_timestamp,
):
    feed = create_trip_update_feed(
        stop_id="9999",
    )

    df = parse_trip_updates(
        feed=feed,
        stop_names={},
        trip_info=sample_trip_info,
        observation_timestamp=observation_timestamp,
    )

    assert df.empty


def test_parse_trip_updates_ignores_non_trip_update_entity(
    sample_stop_names,
    sample_trip_info,
    observation_timestamp,
):
    from google.transit import gtfs_realtime_pb2

    feed = gtfs_realtime_pb2.FeedMessage()

    entity = feed.entity.add()
    entity.id = "vehicle_entity"

    df = parse_trip_updates(
        feed=feed,
        stop_names=sample_stop_names,
        trip_info=sample_trip_info,
        observation_timestamp=observation_timestamp,
    )

    assert df.empty


def test_parse_trip_updates_parses_arrival_and_departure(
    sample_stop_names,
    sample_trip_info,
    observation_timestamp,
):
    from google.transit import gtfs_realtime_pb2

    feed = gtfs_realtime_pb2.FeedMessage()

    entity = feed.entity.add()
    entity.id = "entity_1"

    trip = entity.trip_update.trip
    trip.trip_id = "123"
    trip.start_date = "20260909"

    stop = entity.trip_update.stop_time_update.add()
    stop.stop_id = "1001"
    stop.stop_sequence = 5

    stop.arrival.time = 1757412000
    stop.arrival.delay = 30

    stop.departure.time = 1757412060
    stop.departure.delay = 60

    df = parse_trip_updates(
        feed=feed,
        stop_names=sample_stop_names,
        trip_info=sample_trip_info,
        observation_timestamp=observation_timestamp,
    )

    assert len(df) == 1

    row = df.iloc[0]

    assert row["arrival_delay"] == 30
    assert row["departure_delay"] == 60
    assert row["arrival_time"] is not None
    assert row["departure_time"] is not None
    assert row["line"] == "S1"
    assert row["agency_id"] == "191"


def test_parse_trip_updates_handles_multiple_stops(
    sample_stop_names,
    sample_trip_info,
    observation_timestamp,
):
    from google.transit import gtfs_realtime_pb2

    feed = gtfs_realtime_pb2.FeedMessage()

    entity = feed.entity.add()
    entity.id = "entity_1"

    trip = entity.trip_update.trip
    trip.trip_id = "123"
    trip.start_date = "20260909"

    for sequence, stop_id in enumerate(["1001", "1002"], start=1):
        stop = entity.trip_update.stop_time_update.add()

        stop.stop_id = stop_id
        stop.stop_sequence = sequence

        stop.departure.time = 1757412000 + sequence
        stop.departure.delay = sequence * 10

    df = parse_trip_updates(
        feed=feed,
        stop_names=sample_stop_names,
        trip_info=sample_trip_info,
        observation_timestamp=observation_timestamp,
    )

    assert len(df) == 2
    assert list(df["stop_id"]) == ["1001", "1002"]
    assert list(df["stop_sequence"]) == [1, 2]
    assert list(df["departure_delay"]) == [10, 20]
    assert list(df["agency_id"]) == ["191", "191"]


def test_load_new_data_calls_pipeline():
    fake_feed = Mock()

    fake_trip_info = {
        "123": {
            "line": "S1",
            "agency_id": "191",
        },
    }

    fake_stop_names = {
        "1001": "Marienplatz",
    }

    expected_df = pd.DataFrame({
        "trip_id": ["123"],
        "line": ["S1"],
        "agency_id": ["191"],
        "stop_id": ["1001"],
    })

    with patch(
        "mvv_delay_tracker.realtime.data_loading.load_gtfs_realtime_feed",
        return_value=fake_feed,
    ) as mock_load_feed, patch(
        "mvv_delay_tracker.realtime.data_loading.preprocess_gtfs",
        return_value=(fake_trip_info, fake_stop_names),
    ) as mock_preprocess, patch(
        "mvv_delay_tracker.realtime.data_loading.parse_trip_updates",
        return_value=expected_df,
    ) as mock_parse:

        result = load_new_data(
            data_dir="test_data",
        )

    mock_load_feed.assert_called_once()

    mock_preprocess.assert_called_once_with(
        data_dir="test_data",
    )

    mock_parse.assert_called_once_with(
        feed=fake_feed,
        stop_names=fake_stop_names,
        trip_info=fake_trip_info,
        observation_timestamp=mock_parse.call_args.kwargs[
            "observation_timestamp"
        ],
    )

    assert result.equals(expected_df)