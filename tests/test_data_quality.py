from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from mvv_delay_tracker.realtime.data_quality import (
    append_failures,
    find_departure_failures,
)


def make_observation(departure_time: str, observed_at: str) -> pd.DataFrame:
    return pd.DataFrame({
        "trip_id": ["trip-1"],
        "start_date": ["20260911"],
        "stop_sequence": [1],
        "observation_timestamp": [observed_at],
        "departure_time": [departure_time],
        "departure_delay": [60],
    })


def test_find_departure_failures_accepts_planned_time_plus_delay():
    scheduled = pd.DataFrame({
        "trip_id": ["trip-1"],
        "stop_sequence": [1],
        "departure_time": ["08:00:00"],
    })
    failures = find_departure_failures(
        make_observation(
            "2026-09-11 06:01:00+00:00",
            "2026-09-11 08:00:00+00:00",
        ),
        scheduled,
        datetime(2026, 9, 11, 12, tzinfo=ZoneInfo("UTC")),
        datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("UTC")),
    )

    assert failures.empty


def test_find_departure_failures_records_mismatch():
    scheduled = pd.DataFrame({
        "trip_id": ["trip-1"],
        "stop_sequence": [1],
        "departure_time": ["08:00:00"],
    })
    failures = find_departure_failures(
        make_observation(
            "2026-09-11 06:02:00+00:00",
            "2026-09-11 08:00:00+00:00",
        ),
        scheduled,
        datetime(2026, 9, 11, 12, tzinfo=ZoneInfo("UTC")),
        datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("UTC")),
    )

    assert len(failures) == 1
    assert failures.iloc[0]["difference_seconds"] == 60


def test_find_departure_failures_ignores_observations_older_than_24_hours():
    scheduled = pd.DataFrame({
        "trip_id": ["trip-1"],
        "stop_sequence": [1],
        "departure_time": ["08:00:00"],
    })

    failures = find_departure_failures(
        make_observation(
            "2026-09-11 06:02:00+00:00",
            "2026-09-10 11:59:59+00:00",
        ),
        scheduled,
        datetime(2026, 9, 11, 12, tzinfo=ZoneInfo("UTC")),
        datetime(2026, 9, 10, 12, tzinfo=ZoneInfo("UTC")),
    )

    assert failures.empty


def test_append_failures_creates_header_for_empty_result(tmp_path: Path):
    output_path = tmp_path / "failures.csv"
    append_failures(pd.DataFrame(), output_path)

    assert output_path.exists()
    assert list(pd.read_csv(output_path).columns) == [
        "run_timestamp",
        "trip_id",
        "start_date",
        "stop_sequence",
        "scheduled_departure",
        "realtime_departure",
        "departure_delay_seconds",
        "difference_seconds",
    ]
