import pandas as pd

from mvv_delay_tracker.realtime.data_update import (
    load_existing_realtime_data,
    update_realtime_data,
    save_realtime_data,
)


EXPECTED_COLUMNS = [
    "observation_timestamp",
    "trip_id",
    "start_date",
    "trip_schedule_relationship",
    "stop_schedule_relationship",
    "line",
    "agency_id",
    "agency_name",
    "stop_id",
    "stop_name",
    "stop_sequence",
    "departure_time",
    "departure_delay",
    "arrival_time",
    "arrival_delay",
    "is_prediction",
]


def test_load_existing_realtime_data(tmp_path):
    parquet_path = tmp_path / "realtime.parquet"

    df = pd.DataFrame({
        "observation_timestamp": ["2026-09-09 10:00:00"],
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "trip_schedule_relationship": [pd.NA],
        "stop_schedule_relationship": [pd.NA],
        "line": ["S1"],
        "agency_id": ["191"],
        "agency_name": ["Test Agency"],
        "stop_id": ["1001"],
        "stop_name": ["Marienplatz"],
        "stop_sequence": [1],
        "departure_time": [1757412000],
        "departure_delay": [60],
        "arrival_time": [1757411940],
        "arrival_delay": [30],
        "is_prediction": [False],
    })

    df.to_parquet(parquet_path, index=False)
    agency_path = tmp_path / "agency.txt"
    pd.DataFrame({
        "agency_id": ["191"],
        "agency_name": ["Test Agency"],
    }).to_csv(agency_path, index=False)

    result = load_existing_realtime_data(
        parquet_path,
        agency_path=str(agency_path),
    )

    pd.testing.assert_frame_equal(
        result,
        df.astype({
            "trip_schedule_relationship": "string",
            "stop_schedule_relationship": "string",
        }),
    )


def test_load_existing_realtime_data_file_not_found(tmp_path):
    parquet_path = tmp_path / "missing.parquet"

    result = load_existing_realtime_data(parquet_path)

    assert result.empty
    assert list(result.columns) == EXPECTED_COLUMNS

    assert result["agency_name"].isnull().all()

def test_update_realtime_data_appends_new_data():
    existing_df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "line": ["S1"],
        "agency_id": ["191"],
        "departure_delay": [30],
    })

    new_df = pd.DataFrame({
        "trip_id": ["trip_456"],
        "start_date": ["20260909"],
        "stop_id": ["1002"],
        "line": ["S8"],
        "agency_id": ["364"],
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
    assert list(result["agency_id"]) == [
        "191",
        "364",
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
        "agency_id": ["191"],
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
        "agency_id": ["191"],
        "departure_delay": [120],
        "agency_name": ["Agency 191"],
    })

    result = update_realtime_data(
        existing_df,
        new_df,
    )

    assert len(result) == 1
    assert result.iloc[0]["departure_delay"] == 120
    assert result.iloc[0]["observation_timestamp"] == "2026-09-09 10:05:00"
    assert result.iloc[0]["agency_id"] == "191"
    assert result.iloc[0]["agency_name"] == "Agency 191"


def test_update_realtime_data_deduplicates_by_trip_start_date_stop():
    existing_df = pd.DataFrame({
        "trip_id": ["trip_123", "trip_123"],
        "start_date": ["20260909", "20260909"],
        "stop_id": ["1001", "1002"],
        "line": ["S1", "S1"],
        "agency_id": ["191", "191"],
        "departure_delay": [30, 40],
    })

    new_df = pd.DataFrame({
        "trip_id": ["trip_123", "trip_456"],
        "start_date": ["20260909", "20260909"],
        "stop_id": ["1001", "1003"],
        "line": ["S1", "S8"],
        "agency_id": ["191", "364"],
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
    assert row["agency_id"] == "191"


def test_update_realtime_data_keeps_same_trip_stop_for_different_agencies():
    existing_df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "agency_id": ["191"],
        "departure_delay": [30],
    })
    new_df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "agency_id": ["364"],
        "departure_delay": [60],
    })

    result = update_realtime_data(existing_df, new_df)

    assert len(result) == 2
    assert set(result["agency_id"]) == {"191", "364"}


def test_update_realtime_data_preserves_order():
    existing_df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "agency_id": ["191"],
    })

    new_df = pd.DataFrame({
        "trip_id": ["trip_456"],
        "start_date": ["20260909"],
        "stop_id": ["1002"],
        "agency_id": ["364"],
    })

    result = update_realtime_data(
        existing_df,
        new_df,
    )

    assert list(result["trip_id"]) == [
        "trip_123",
        "trip_456",
    ]

    assert list(result["agency_id"]) == [
        "191",
        "364",
    ]


def test_update_realtime_data_prediction_is_replaced_by_confirmation():
    existing_df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "departure_delay": [30],
        "is_prediction": [True],
    })

    new_df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "departure_delay": [45],
        "is_prediction": [False],
    })

    result = update_realtime_data(existing_df, new_df)

    assert len(result) == 1
    assert result.iloc[0]["departure_delay"] == 45
    assert result.iloc[0]["is_prediction"] == False


def test_update_realtime_data_confirmation_is_not_replaced_by_prediction():
    existing_df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "departure_delay": [30],
        "is_prediction": [False],
    })

    new_df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "departure_delay": [999],
        "is_prediction": [True],
    })

    result = update_realtime_data(existing_df, new_df)

    assert len(result) == 1
    assert result.iloc[0]["departure_delay"] == 30
    assert result.iloc[0]["is_prediction"] == False


def test_save_realtime_data(tmp_path):
    parquet_path = tmp_path / "realtime.parquet"

    df = pd.DataFrame({
        "trip_id": ["trip_123"],
        "start_date": ["20260909"],
        "stop_id": ["1001"],
        "line": ["S1"],
        "agency_id": ["191"],
        "departure_delay": [60],
    })

    save_realtime_data(
        df,
        parquet_path,
    )

    assert parquet_path.exists()

    result = pd.read_parquet(parquet_path)

    pd.testing.assert_frame_equal(result, df)