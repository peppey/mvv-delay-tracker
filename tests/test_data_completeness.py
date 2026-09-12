from datetime import datetime

import pandas as pd

from mvv_delay_tracker.realtime.data_completeness import (
    calculate_line_completeness,
    calculate_trip_completeness,
    load_munich_schedule,
)


def test_load_munich_schedule_uses_geographic_stops(tmp_path):
    pd.DataFrame({
        "trip_id": ["munich-s6", "german-s6"],
        "stop_id": ["munich-stop", "other-stop"],
        "departure_time": ["08:00:00", "08:00:00"],
    }).to_csv(tmp_path / "stop_times.txt", index=False)
    pd.DataFrame({
        "trip_id": ["munich-s6", "german-s6"],
        "service_id": ["weekday", "weekday"],
        "route_id": ["route-s6", "route-s6"],
    }).to_csv(tmp_path / "trips.txt", index=False)
    pd.DataFrame({
        "route_id": ["route-s6"],
        "route_short_name": ["S6"],
    }).to_csv(tmp_path / "routes.txt", index=False)
    pd.DataFrame({"stop_id": ["munich-stop"]}).to_csv(
        tmp_path / "munich_stops.csv", index=False
    )

    result = load_munich_schedule(tmp_path)

    assert list(result["trip_id"]) == ["munich-s6"]


def test_calculate_trip_completeness_counts_observations_in_period_only():
    planned = pd.DataFrame({
        "trip_id": ["trip-1"],
        "service_date": ["20260911"],
    })
    realtime = pd.DataFrame({
        "trip_id": ["trip-1"],
        "start_date": ["20260911"],
        "observation_timestamp": ["2026-09-11 11:00:00"],
        "departure_time": ["2026-09-11 10:30:00"],
        "departure_delay": [pd.NA],
    })

    result = calculate_trip_completeness(
        planned,
        realtime,
        datetime(2026, 9, 11, 10),
        datetime(2026, 9, 11, 12),
    )

    assert result["planned_trips"] == 1
    assert result["observed_trips"] == 1
    assert result["observed_trips_with_delay"] == 0
    assert result["completeness_percent"] == 100.0


def test_calculate_line_completeness_counts_missing_trips_by_line():
    planned = pd.DataFrame({
        "trip_id": ["trip-1", "trip-2", "trip-3"],
        "service_date": ["20260911"] * 3,
        "line": ["S6", "S6", "U3"],
    })
    realtime = pd.DataFrame({
        "trip_id": ["trip-1"],
        "start_date": ["20260911"],
        "observation_timestamp": ["2026-09-11 11:00:00"],
    })

    result = calculate_line_completeness(
        planned,
        realtime,
        datetime(2026, 9, 11, 10),
        datetime(2026, 9, 11, 12),
    ).set_index("line")

    assert result.loc["S6", "planned_trips"] == 2
    assert result.loc["S6", "observed_trips"] == 1
    assert result.loc["S6", "missing_trips"] == 1
    assert result.loc["U3", "missing_trips"] == 1