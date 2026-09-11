from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from mvv_delay_tracker.realtime.data_update import load_existing_realtime_data


COMPLETENESS_PATH = Path("data/quality/munich_trip_completeness.csv")
COMPLETENESS_PLOT_PATH = Path("docs/munich_trip_completeness.png")
LOCAL_TIMEZONE = "Europe/Berlin"
REPORT_COLUMNS = [
    "period_start",
    "period_end",
    "planned_trips",
    "observed_trips",
    "missing_trips",
    "completeness_percent",
]


def _gtfs_time_to_seconds(value: str) -> int:
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def load_munich_schedule(
    static_data_directory: Path = Path("data/static"),
) -> pd.DataFrame:
    """Load trips with at least one stop inside Munich's city boundary."""
    stop_times = pd.read_csv(
        static_data_directory / "stop_times.txt",
        usecols=["trip_id", "stop_id", "departure_time"],
        dtype=str,
    )
    trips = pd.read_csv(
        static_data_directory / "trips.txt",
        usecols=["trip_id", "service_id"],
        dtype=str,
    )
    munich_stops = pd.read_csv(
        static_data_directory / "munich_stops.csv",
        usecols=["stop_id"],
        dtype=str,
    )["stop_id"]
    schedule = (
        stop_times
        .loc[stop_times["stop_id"].isin(set(munich_stops))]
        .merge(trips, on="trip_id", how="inner")
    )
    schedule["departure_seconds"] = schedule["departure_time"].map(
        _gtfs_time_to_seconds
    )
    return (
        schedule.groupby(["trip_id", "service_id"], as_index=False)
        ["departure_seconds"].min()
    )


def _active_service_dates(
    static_data_directory: Path,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    """Expand GTFS calendar rules into service dates in the requested range."""
    dates = pd.date_range(start_date, end_date, freq="D")
    calendar = pd.read_csv(
        static_data_directory / "calendar.txt",
        dtype={"service_id": str},
    )
    rows: list[dict[str, object]] = []
    for _, service in calendar.iterrows():
        service_start = datetime.strptime(
            str(service["start_date"]), "%Y%m%d"
        ).date()
        service_end = datetime.strptime(
            str(service["end_date"]), "%Y%m%d"
        ).date()
        for timestamp in dates:
            service_date = timestamp.date()
            if not (service_start <= service_date <= service_end):
                continue
            weekday = timestamp.day_name().lower()
            if str(service[weekday]) == "1":
                rows.append({
                    "service_id": service["service_id"],
                    "service_date": service_date,
                })
    active = pd.DataFrame(rows)
    exceptions_path = static_data_directory / "calendar_dates.txt"
    if exceptions_path.exists():
        exceptions = pd.read_csv(exceptions_path, dtype={"service_id": str})
        exceptions["service_date"] = pd.to_datetime(
            exceptions["date"].astype(str), format="%Y%m%d"
        ).dt.date
        exceptions = exceptions.loc[
            exceptions["service_date"].between(start_date, end_date)
        ]
        for _, exception in exceptions.iterrows():
            key = (
                active["service_id"].eq(exception["service_id"])
                & active["service_date"].eq(exception["service_date"])
            ) if not active.empty else pd.Series(dtype=bool)
            if exception["exception_type"] == 1 and not key.any():
                active = pd.concat([
                    active,
                    pd.DataFrame([{
                        "service_id": exception["service_id"],
                        "service_date": exception["service_date"],
                    }]),
                ], ignore_index=True)
            elif exception["exception_type"] == 2:
                active = active.loc[~key]
    return active.drop_duplicates()


def expand_schedule(
    schedule: pd.DataFrame,
    static_data_directory: Path,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Create scheduled trip instances between two local timestamps."""
    service_dates = _active_service_dates(
        static_data_directory,
        start.date(),
        end.date(),
    )
    planned = schedule.merge(service_dates, on="service_id", how="inner")
    planned["scheduled_departure"] = planned.apply(
        lambda row: datetime.combine(
            row["service_date"], datetime.min.time()
        ) + timedelta(seconds=int(row["departure_seconds"])),
        axis=1,
    )
    return planned.loc[
        planned["scheduled_departure"].between(start, end, inclusive="left")
    ][["trip_id", "service_date", "scheduled_departure"]].drop_duplicates()


def calculate_trip_completeness(
    planned_trips: pd.DataFrame,
    realtime_data: pd.DataFrame,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, object]:
    """Compare planned trip instances with trip instances seen in the feed."""
    planned = planned_trips.copy()
    planned["trip_key"] = (
        planned["trip_id"].astype(str)
        + ":"
        + planned["service_date"].astype(str).str.replace("-", "", regex=False)
    )
    observations = realtime_data.copy()
    observations["observation_timestamp"] = pd.to_datetime(
        observations["observation_timestamp"], errors="coerce"
    )
    observations = observations.loc[
        observations["observation_timestamp"].between(
            period_start, period_end, inclusive="left"
        )
    ]
    observed_keys = set(
        observations["trip_id"].astype(str)
        + ":"
        + observations["start_date"].astype(str)
    )
    planned_count = planned["trip_key"].nunique()
    observed_count = len(set(planned["trip_key"]) & observed_keys)
    return {
        "period_start": period_start.isoformat(sep=" "),
        "period_end": period_end.isoformat(sep=" "),
        "planned_trips": planned_count,
        "observed_trips": observed_count,
        "missing_trips": planned_count - observed_count,
        "completeness_percent": round(
            100 * observed_count / planned_count, 2
        ) if planned_count else 0.0,
    }


def build_completeness_report(
    realtime_data: pd.DataFrame,
    static_data_directory: Path = Path("data/static"),
    now: datetime | None = None,
) -> pd.DataFrame:
    """Build one report row per elapsed 24-hour period."""
    timestamps = pd.to_datetime(
        realtime_data["observation_timestamp"], errors="coerce"
    ).dropna()
    if timestamps.empty:
        return pd.DataFrame(columns=REPORT_COLUMNS)
    first = timestamps.min().to_pydatetime().replace(tzinfo=None)
    last = (now or timestamps.max().to_pydatetime()).replace(tzinfo=None)
    schedule = load_munich_schedule(static_data_directory)
    rows = []
    period_start = first
    while period_start < last:
        period_end = min(period_start + timedelta(hours=24), last)
        planned = expand_schedule(
            schedule, static_data_directory, period_start, period_end
        )
        rows.append(calculate_trip_completeness(
            planned, realtime_data, period_start, period_end
        ))
        period_start += timedelta(hours=24)
    return pd.DataFrame(rows, columns=REPORT_COLUMNS)


def save_completeness_report(
    report: pd.DataFrame,
    output_path: Path = COMPLETENESS_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_path, index=False)


def plot_completeness(
    report: pd.DataFrame,
    output_path: Path = COMPLETENESS_PLOT_PATH,
) -> None:
    """Plot planned and observed Munich trips for each report period."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(11, 6))
    if report.empty:
        axis.text(0.5, 0.5, "Keine Realtime-Daten vorhanden", ha="center")
        axis.set_axis_off()
    else:
        labels = pd.to_datetime(report["period_start"]).dt.strftime("%d.%m. %H:%M")
        x = range(len(report))
        width = 0.36
        axis.bar([value - width / 2 for value in x], report["planned_trips"],
                 width, label="Geplant", color="#315a7d")
        axis.bar([value + width / 2 for value in x], report["observed_trips"],
                 width, label="Im Feed", color="#e07a5f")
        axis.set_xticks(list(x), labels, rotation=30, ha="right")
        axis.set_ylabel("Anzahl Fahrten")
        axis.set_title("Vollständigkeit der Münchner Fahrten im Realtime-Feed")
        axis.legend(frameon=False)
        axis.grid(axis="y", alpha=0.2)
        for index, row in report.iterrows():
            axis.text(index, row["planned_trips"],
                      f'{row["completeness_percent"]:.1f} %',
                      ha="center", va="bottom", fontsize=9)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def run_data_completeness_check(
    realtime_path: str = "data/realtime/mvv_realtime.parquet",
    static_data_directory: Path = Path("data/static"),
    output_path: Path = COMPLETENESS_PATH,
    plot_path: Path = COMPLETENESS_PLOT_PATH,
) -> pd.DataFrame:
    """Create and save the current completeness report and plot."""
    realtime_data = load_existing_realtime_data(realtime_path)
    report = build_completeness_report(
        realtime_data,
        static_data_directory,
    )
    save_completeness_report(report, output_path)
    plot_completeness(report, plot_path)
    return report