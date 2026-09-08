import pandas as pd
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from mvv_delay_tracker.data_loading import (
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
def sample_trip_lines():
    return {
        "123": "S1",
        "456": "S8",
    }


@pytest.fixture
def observation_timestamp():
    return datetime(2026, 9, 9, 10, 0, 0)


def test_load_gtfs_realtime_feed_success():
    response = Mock()
    response.content = b""
    response.raise_for_status = Mock()

    with patch(
        "mvv_delay_tracker.data_loading.requests.get",
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
        "mvv_delay_tracker.data_loading.requests.get",
        return_value=response,
    ):

        with pytest.raises(Exception, match="HTTP error"):
            load_gtfs_realtime_feed("http://test-url")


def test_preprocess_gtfs_filters_agencies(tmp_path):
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

    routes.to_csv(tmp_path / "routes.txt", index=False)
    trips.to_csv(tmp_path / "trips.txt", index=False)
    stops.to_csv(tmp_path / "munich_stops.csv", index=False)

    trip_lines, stop_names = preprocess_gtfs(
        data_dir=str(tmp_path),
        munich_geojson_path="unused.geojson",
        munich_agencies=["191", "364"],
    )

    assert trip_lines == {
        "101": "S1",
        "102": "S8",
    }

    assert "103" not in trip_lines

    assert stop_names == {
        "1001": "Marienplatz",
        "1002": "Karlsplatz",
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

    routes.to_csv(tmp_path / "routes.txt", index=False)
    trips.to_csv(tmp_path / "trips.txt", index=False)
    stops.to_csv(tmp_path / "munich_stops.csv", index=False)

    trip_lines, stop_names = preprocess_gtfs(
        data_dir=str(tmp_path),
        munich_geojson_path="unused.geojson",
        munich_agencies=["191"],
    )

    assert trip_lines == {"456": "S1"}
    assert stop_names == {"789": "Test Stop"}


def test_preprocess_gtfs_excludes_trips_from_other_agencies(tmp_path):
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

    routes.to_csv(tmp_path / "routes.txt", index=False)
    trips.to_csv(tmp_path / "trips.txt", index=False)
    stops.to_csv(tmp_path / "munich_stops.csv", index=False)

    trip_lines, _ = preprocess_gtfs(
        data_dir=str(tmp_path),
        munich_geojson_path="unused.geojson",
        munich_agencies=["191"],
    )

    assert "trip_munich" in trip_lines
    assert "trip_outside" not in trip_lines


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
    sample_trip_lines,
    observation_timestamp,
):
    feed = create_trip_update_feed()

    df = parse_trip_updates(
        feed=feed,
        stop_names=sample_stop_names,
        trip_lines=sample_trip_lines,
        observation_timestamp=observation_timestamp,
    )

    assert len(df) == 1

    row = df.iloc[0]

    assert row["trip_id"] == "123"
    assert row["start_date"] == "20260909"
    assert row["line"] == "S1"
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
        trip_lines={},
        observation_timestamp=observation_timestamp,
    )

    assert df.empty


def test_parse_trip_updates_ignores_unknown_stop(
    sample_trip_lines,
    observation_timestamp,
):
    feed = create_trip_update_feed(
        stop_id="9999",
    )

    df = parse_trip_updates(
        feed=feed,
        stop_names={},
        trip_lines=sample_trip_lines,
        observation_timestamp=observation_timestamp,
    )

    assert df.empty


def test_parse_trip_updates_ignores_non_trip_update_entity(
    sample_stop_names,
    sample_trip_lines,
    observation_timestamp,
):
    from google.transit import gtfs_realtime_pb2

    feed = gtfs_realtime_pb2.FeedMessage()

    entity = feed.entity.add()
    entity.id = "vehicle_entity"

    df = parse_trip_updates(
        feed=feed,
        stop_names=sample_stop_names,
        trip_lines=sample_trip_lines,
        observation_timestamp=observation_timestamp,
    )

    assert df.empty


def test_parse_trip_updates_parses_arrival_and_departure(
    sample_stop_names,
    sample_trip_lines,
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
        trip_lines=sample_trip_lines,
        observation_timestamp=observation_timestamp,
    )

    assert len(df) == 1

    row = df.iloc[0]

    assert row["arrival_delay"] == 30
    assert row["departure_delay"] == 60
    assert row["arrival_time"] is not None
    assert row["departure_time"] is not None


def test_parse_trip_updates_handles_multiple_stops(
    sample_stop_names,
    sample_trip_lines,
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
        trip_lines=sample_trip_lines,
        observation_timestamp=observation_timestamp,
    )

    assert len(df) == 2
    assert list(df["stop_id"]) == ["1001", "1002"]
    assert list(df["stop_sequence"]) == [1, 2]
    assert list(df["departure_delay"]) == [10, 20]


def test_load_new_data_calls_pipeline():
    fake_feed = Mock()

    fake_trip_lines = {
        "123": "S1",
    }

    fake_stop_names = {
        "1001": "Marienplatz",
    }

    expected_df = pd.DataFrame({
        "trip_id": ["123"],
        "line": ["S1"],
        "stop_id": ["1001"],
    })

    with patch(
        "mvv_delay_tracker.data_loading.load_gtfs_realtime_feed",
        return_value=fake_feed,
    ) as mock_load_feed, patch(
        "mvv_delay_tracker.data_loading.preprocess_gtfs",
        return_value=(fake_trip_lines, fake_stop_names),
    ) as mock_preprocess, patch(
        "mvv_delay_tracker.data_loading.parse_trip_updates",
        return_value=expected_df,
    ) as mock_parse:

        result = load_new_data(
            data_dir="test_data",
            munich_geojson_path="test.geojson",
        )

    mock_load_feed.assert_called_once()

    mock_preprocess.assert_called_once_with(
        data_dir="test_data",
        munich_geojson_path="test.geojson",
    )

    mock_parse.assert_called_once()

    assert result.equals(expected_df)