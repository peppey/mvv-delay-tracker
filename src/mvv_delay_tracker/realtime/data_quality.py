from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from mvv_delay_tracker.realtime.data_update import load_existing_realtime_data
from mvv_delay_tracker.static.static_data import download_static_file


FAILURE_PATH = Path("data/quality/realtime_departure_failures.csv")
COMPARISON_TOLERANCE_SECONDS = 1
LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")
FAILURE_COLUMNS = [
    "run_timestamp",
    "trip_id",
    "start_date",
    "stop_sequence",
    "scheduled_departure",
    "realtime_departure",
    "departure_delay_seconds",
    "difference_seconds",
]


def _gtfs_time_to_seconds(value: str) -> int:
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def _to_local_naive(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    if parsed.dt.tz is None:
        return parsed
    return parsed.dt.tz_convert(LOCAL_TIMEZONE).dt.tz_localize(None)


def load_stop_times(
    stop_times_bytes: bytes,
    static_data_directory: Path = Path("data/static"),
) -> pd.DataFrame:
    """Load the fields needed to compare scheduled departures."""
    stop_times = pd.read_csv(
        BytesIO(stop_times_bytes),
        usecols=["trip_id", "stop_sequence", "departure_time"],
        dtype={"trip_id": str, "stop_sequence": "Int64"},
    )
    trips = pd.read_csv(
        static_data_directory / "trips.txt",
        usecols=["trip_id", "route_id"],
        dtype=str,
    )
    routes = pd.read_csv(
        static_data_directory / "routes.txt",
        usecols=["route_id", "agency_id", "route_short_name"],
        dtype=str,
    )
    return (
        stop_times
        .merge(trips, on="trip_id", how="inner")
        .merge(routes, on="route_id", how="inner")
        .rename(columns={"route_short_name": "line"})
    )


def find_departure_failures(
    realtime_data: pd.DataFrame,
    stop_times: pd.DataFrame,
    run_timestamp: datetime,
    window_start: datetime,
    tolerance_seconds: int = COMPARISON_TOLERANCE_SECONDS,
) -> pd.DataFrame:
    """Find recent observations that disagree with scheduled time plus delay."""
    observations = realtime_data.copy()
    observations["observation_timestamp"] = _to_local_naive(
        observations["observation_timestamp"]
    )
    observations["departure_time"] = _to_local_naive(
        observations["departure_time"]
    )
    window_start_local = pd.Timestamp(window_start)
    run_timestamp_local = pd.Timestamp(run_timestamp)
    if window_start_local.tzinfo is not None:
        window_start_local = window_start_local.tz_convert(
            LOCAL_TIMEZONE
        ).tz_localize(None)
    if run_timestamp_local.tzinfo is not None:
        run_timestamp_local = run_timestamp_local.tz_convert(
            LOCAL_TIMEZONE
        ).tz_localize(None)
    observations = observations.loc[
        observations["observation_timestamp"].between(
            window_start_local,
            run_timestamp_local,
            inclusive="both",
        )
    ].dropna(
        subset=[
            "trip_id",
            "start_date",
            "stop_sequence",
            "departure_time",
            "departure_delay",
        ]
    )

    scheduled = stop_times.copy()
    scheduled["stop_sequence"] = scheduled["stop_sequence"].astype("Int64")
    scheduled["scheduled_seconds"] = scheduled["departure_time"].map(
        _gtfs_time_to_seconds
    )
    scheduled = scheduled.set_index(
        ["trip_id", "agency_id", "line", "stop_sequence"]
    )
    failures: list[dict[str, object]] = []

    for _, observation in observations.iterrows():
        trip_id = str(observation["trip_id"])
        start_date = str(observation["start_date"])
        service_date = datetime.strptime(start_date, "%Y%m%d").date()
        key = (
            trip_id,
            str(observation["agency_id"]),
            str(observation["line"]),
            int(observation["stop_sequence"]),
        )
        if key not in scheduled.index:
            continue

        scheduled_seconds = int(scheduled.loc[key, "scheduled_seconds"])
        departure_delay = int(observation["departure_delay"])
        expected_timestamp = datetime.combine(
            service_date,
            datetime.min.time(),
        ) + timedelta(seconds=scheduled_seconds + departure_delay)
        actual_timestamp = observation["departure_time"].to_pydatetime()
        difference_seconds = int(
            (actual_timestamp - expected_timestamp).total_seconds()
        )

        if abs(difference_seconds) > tolerance_seconds:
            failures.append({
                "run_timestamp": run_timestamp.isoformat(),
                "trip_id": trip_id,
                "start_date": start_date,
                "stop_sequence": int(observation["stop_sequence"]),
                "scheduled_departure": expected_timestamp.isoformat(),
                "realtime_departure": actual_timestamp.isoformat(),
                "departure_delay_seconds": departure_delay,
                "difference_seconds": difference_seconds,
            })

    return pd.DataFrame(failures)


def append_failures(
    failures: pd.DataFrame,
    output_path: Path = FAILURE_PATH,
) -> None:
    """Append failures to a human-readable CSV history."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if failures.empty:
        if not output_path.exists():
            pd.DataFrame(columns=FAILURE_COLUMNS).to_csv(
                output_path,
                index=False,
            )
        return

    write_header = not output_path.exists()
    failures.to_csv(output_path, mode="a", header=write_header, index=False)


def run_data_quality_check(
    realtime_path: str = "data/realtime/mvv_realtime.parquet",
    output_path: Path = FAILURE_PATH,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Check the last 24 hours of stored realtime observations."""
    run_timestamp = now or datetime.now(timezone.utc)
    realtime_data = load_existing_realtime_data(realtime_path)
    stop_times = load_stop_times(download_static_file("stop_times.txt"))
    failures = find_departure_failures(
        realtime_data,
        stop_times,
        run_timestamp,
        run_timestamp - timedelta(hours=24),
    )
    append_failures(failures, output_path)
    return failures


def main() -> None:
    failures = run_data_quality_check()
    print(f"Departure quality check failures: {len(failures)}")


if __name__ == "__main__":
    main()