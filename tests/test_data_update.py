import pandas as pd

from mvv_delay_tracker.data_update import (
    load_existing_realtime_data,
    update_realtime_data,
    save_realtime_data,
)


EXPECTED_COLUMNS = [
    "observation_timestamp",
    "trip_id",
    "start_date",
    "line",
    "stop_id",
    "stop_name",
    "stop_sequence",
    "departure_time",
    "departure_delay",
    "arrival_time",
    "arrival_delay",
]


def test_load_existing_realtime_data(tmp_path):
    parquet_path = tmp_path / "realtime.parquet"

    df = pd.DataFrame({
        "observation_timestamp": ["2026-09-09 10:00:00"],
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "line": ["S1"],
        "stop_id": ["1001"],
        "stop_name": ["Marienplatz"],
        "stop_sequence": [1],
        "departure_time": [1757412000],
        "departure_delay": [60],
        "arrival_time": [1757411940],
        "arrival_delay": [30],
    })

    df.to_parquet(parquet_path, index=False)

    result = load_existing_realtime_data(parquet_path)

    pd.testing.assert_frame_equal(result, df)


def test_load_existing_realtime_data_file_not_found(tmp_path):
    parquet_path = tmp_path / "missing.parquet"

    result = load_existing_realtime_data(parquet_path)

    assert result.empty
    assert list(result.columns) == EXPECTED_COLUMNS


def test_update_realtime_data_appends_new_data():
    existing_df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "line": ["S1"],
        "departure_delay": [30],
    })

    new_df = pd.DataFrame({
        "trip_id": ["trip_456"],
        "start_date": ["20260909"],
        "stop_id": ["1002"],
        "line": ["S8"],
        "departure_delay": [60],
    })

    result = update_realtime_data(
        existing_df,
        new_df,
    )

    assert len(result) == 2
    assert list(result["trip_id"]) == [
        "trip_123",
        "trip_456",
    ]


def test_update_realtime_data_keeps_latest_observation():
    existing_df = pd.DataFrame({
        "observation_timestamp": [
            "2026-09-09 10:00:00",
        ],
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "line": ["S1"],
        "departure_delay": [30],
    })

    new_df = pd.DataFrame({
        "observation_timestamp": [
            "2026-09-09 10:05:00",
        ],
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "line": ["S1"],
        "departure_delay": [120],
    })

    result = update_realtime_data(
        existing_df,
        new_df,
    )

    assert len(result) == 1
    assert result.iloc[0]["departure_delay"] == 120
    assert result.iloc[0]["observation_timestamp"] == "2026-09-09 10:05:00"


def test_update_realtime_data_deduplicates_by_trip_start_date_stop():
    existing_df = pd.DataFrame({
        "trip_id": ["trip_123", "trip_123"],
        "start_date": ["20260909", "20260909"],
        "stop_id": ["1001", "1002"],
        "departure_delay": [30, 40],
    })

    new_df = pd.DataFrame({
        "trip_id": ["trip_123", "trip_456"],
        "start_date": ["20260909", "20260909"],
        "stop_id": ["1001", "1003"],
        "departure_delay": [90, 60],
    })

    result = update_realtime_data(
        existing_df,
        new_df,
    )

    assert len(result) == 3

    row = result[
        (result["trip_id"] == "trip_123")
        & (result["stop_id"] == "1001")
    ].iloc[0]

    assert row["departure_delay"] == 90


def test_update_realtime_data_preserves_order():
    existing_df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
    })

    new_df = pd.DataFrame({
        "trip_id": ["trip_456"],
        "start_date": ["20260909"],
        "stop_id": ["1002"],
    })

    result = update_realtime_data(
        existing_df,
        new_df,
    )

    assert list(result["trip_id"]) == [
        "trip_123",
        "trip_456",
    ]


def test_save_realtime_data(tmp_path):
    parquet_path = tmp_path / "realtime.parquet"

    df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "departure_delay": [60],
    })

    save_realtime_data(
        df,
        parquet_path,
    )

    assert parquet_path.exists()

    result = pd.read_parquet(parquet_path)

    pd.testing.assert_frame_equal(result, df)
