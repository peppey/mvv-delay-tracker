from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from mvv_delay_tracker.realtime.data_update import load_existing_realtime_data


logger = logging.getLogger(__name__)


COMPLETENESS_PATH = Path("data/quality/munich_trip_completeness.csv")
COMPLETENESS_PLOT_PATH = Path("docs/munich_trip_completeness.png")
LINE_COMPLETENESS_PATH = Path(
    "data/quality/munich_trip_completeness_by_line.csv"
)
LINE_COMPLETENESS_PLOT_PATH = Path(
    "docs/munich_trip_completeness_by_line.png"
)
LOCAL_TIMEZONE = "Europe/Berlin"
REPORT_COLUMNS = [
    "period_start",
    "period_end",
    "planned_trips",
    "observed_trips",
    "observed_trips_with_delay",
    "missing_trips",
    "completeness_percent",
]
LINE_REPORT_COLUMNS = [
    "period_start",
    "period_end",
    "line",
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
    stop_times_chunk_size: int = 500_000,
) -> pd.DataFrame:
    """Load trips with at least one stop inside Munich's city boundary."""
    trips = pd.read_csv(
        static_data_directory / "trips.txt",
        usecols=["trip_id", "service_id", "route_id"],
        dtype=str,
    )
    routes = pd.read_csv(
        static_data_directory / "routes.txt",
        usecols=["route_id", "route_short_name"],
        dtype=str,
    )
    munich_stop_ids = set(pd.read_csv(
        static_data_directory / "munich_stops.csv",
        usecols=["stop_id"],
        dtype=str,
    )["stop_id"])

    # stop_times.txt covers all of Germany, so it's filtered chunk by chunk
    # instead of being fully loaded into memory at once.
    stop_times_chunks = [
        chunk.loc[chunk["stop_id"].isin(munich_stop_ids)]
        for chunk in pd.read_csv(
            static_data_directory / "stop_times.txt",
            usecols=["trip_id", "stop_id", "departure_time"],
            dtype=str,
            chunksize=stop_times_chunk_size,
        )
    ]
    stop_times = (
        pd.concat(stop_times_chunks, ignore_index=True)
        if stop_times_chunks
        else pd.DataFrame(columns=["trip_id", "stop_id", "departure_time"])
    )
    schedule = (
        stop_times
        .merge(trips, on="trip_id", how="inner")
        .merge(routes, on="route_id", how="inner")
    )
    schedule["line"] = schedule["route_short_name"].fillna("Unbekannt")
    schedule["departure_seconds"] = schedule["departure_time"].map(
        _gtfs_time_to_seconds
    )
    return (
        schedule.groupby(
            ["trip_id", "service_id", "line"], as_index=False
        )["departure_seconds"].min()
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
    ][
        ["trip_id", "service_date", "scheduled_departure", "line"]
    ].drop_duplicates()


def _observed_trip_keys(
    realtime_data: pd.DataFrame,
    period_start: datetime,
    period_end: datetime,
    require_delay: bool = False,
) -> set[str]:
    observations = realtime_data.copy()
    observations["observation_timestamp"] = pd.to_datetime(
        observations["observation_timestamp"], errors="coerce"
    )
    observations = observations.loc[
        observations["observation_timestamp"].between(
            period_start, period_end, inclusive="both"
        )
    ]
    if require_delay:
        if "departure_delay" not in observations.columns:
            return set()
        observations = observations.dropna(subset=["departure_delay"])
    return set(
        observations["trip_id"].astype(str)
        + ":"
        + observations["start_date"].astype(str)
    )


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
    observed_keys = _observed_trip_keys(realtime_data, period_start, period_end)
    observed_keys_with_delay = _observed_trip_keys(
        realtime_data, period_start, period_end, require_delay=True
    )
    planned_count = planned["trip_key"].nunique()
    observed_count = len(set(planned["trip_key"]) & observed_keys)
    return {
        "period_start": period_start.isoformat(sep=" "),
        "period_end": period_end.isoformat(sep=" "),
        "planned_trips": planned_count,
        "observed_trips": observed_count,
        "observed_trips_with_delay": len(
            set(planned["trip_key"]) & observed_keys_with_delay
        ),
        "missing_trips": planned_count - observed_count,
        "completeness_percent": round(
            100 * observed_count / planned_count, 2
        ) if planned_count else 0.0,
    }


def calculate_line_completeness(
    planned_trips: pd.DataFrame,
    realtime_data: pd.DataFrame,
    period_start: datetime,
    period_end: datetime,
) -> pd.DataFrame:
    """Count planned, observed, and missing trips separately by line."""
    if planned_trips.empty:
        return pd.DataFrame(columns=LINE_REPORT_COLUMNS)

    planned = planned_trips.copy()
    planned["trip_key"] = (
        planned["trip_id"].astype(str)
        + ":"
        + planned["service_date"].astype(str).str.replace("-", "", regex=False)
    )
    observed_keys = _observed_trip_keys(
        realtime_data, period_start, period_end
    )
    planned["observed"] = planned["trip_key"].isin(observed_keys)
    result = planned.groupby("line", as_index=False).agg(
        planned_trips=("trip_key", "nunique"),
        observed_trips=("observed", "sum"),
    )
    result["missing_trips"] = (
        result["planned_trips"] - result["observed_trips"]
    )
    result["completeness_percent"] = (
        100 * result["observed_trips"] / result["planned_trips"]
    ).round(2)
    result.insert(0, "period_end", period_end.isoformat(sep=" "))
    result.insert(0, "period_start", period_start.isoformat(sep=" "))
    return result[LINE_REPORT_COLUMNS]


def build_completeness_report(
    realtime_data: pd.DataFrame,
    static_data_directory: Path = Path("data/static"),
    now: datetime | None = None,
    start_from: datetime | None = None,
) -> pd.DataFrame:
    """Build one report row per elapsed 24-hour period.

    ``start_from`` resumes the report from a given period instead of the
    first ever recorded departure, so previously computed periods aren't
    recalculated on every run.
    """
    observation_timestamps = pd.to_datetime(
        realtime_data["observation_timestamp"], errors="coerce"
    ).dropna()
    departure_times = pd.to_datetime(
        realtime_data["departure_time"], errors="coerce"
    ).dropna()
    if observation_timestamps.empty or departure_times.empty:
        return pd.DataFrame(columns=REPORT_COLUMNS)
    first = departure_times.min().to_pydatetime().replace(tzinfo=None)
    if start_from is not None:
        first = max(first, start_from)
    last = (now or observation_timestamps.max().to_pydatetime()).replace(
        tzinfo=None
    )
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
        logger.info(
            "Trip completeness period %s - %s done.", period_start, period_end
        )
        period_start += timedelta(hours=24)
    return pd.DataFrame(rows, columns=REPORT_COLUMNS)


def build_line_completeness_report(
    realtime_data: pd.DataFrame,
    static_data_directory: Path = Path("data/static"),
    now: datetime | None = None,
    start_from: datetime | None = None,
) -> pd.DataFrame:
    """Build the completeness report grouped by line and 24-hour period.

    ``start_from`` resumes the report from a given period instead of the
    first ever recorded departure, so previously computed periods aren't
    recalculated on every run.
    """
    observation_timestamps = pd.to_datetime(
        realtime_data["observation_timestamp"], errors="coerce"
    ).dropna()
    departure_times = pd.to_datetime(
        realtime_data["departure_time"], errors="coerce"
    ).dropna()
    if observation_timestamps.empty or departure_times.empty:
        return pd.DataFrame(columns=LINE_REPORT_COLUMNS)
    first = departure_times.min().to_pydatetime().replace(tzinfo=None)
    if start_from is not None:
        first = max(first, start_from)
    last = (now or observation_timestamps.max().to_pydatetime()).replace(
        tzinfo=None
    )
    schedule = load_munich_schedule(static_data_directory)
    reports = []
    period_start = first
    while period_start < last:
        period_end = min(period_start + timedelta(hours=24), last)
        planned = expand_schedule(
            schedule, static_data_directory, period_start, period_end
        )
        reports.append(calculate_line_completeness(
            planned, realtime_data, period_start, period_end
        ))
        logger.info(
            "Line completeness period %s - %s done.", period_start, period_end
        )
        period_start += timedelta(hours=24)
    if not reports:
        return pd.DataFrame(columns=LINE_REPORT_COLUMNS)
    return pd.concat(reports, ignore_index=True)[LINE_REPORT_COLUMNS]


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
    """Plot planned and observed Munich trips as lines and an area."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(11, 6))
    figure.patch.set_facecolor("#FFFFFF")
    axis.set_facecolor("#FFFFFF")
    if report.empty:
        axis.text(0.5, 0.5, "Keine Realtime-Daten vorhanden", ha="center")
        axis.set_axis_off()
    else:
        report = report.copy()
        report["period_start"] = pd.to_datetime(report["period_start"])
        x = list(range(len(report)))
        planned = report["planned_trips"]
        observed = report["observed_trips"]
        observed_with_delay = report["observed_trips_with_delay"]
        axis.fill_between(x, planned, color="#B2DFDB", alpha=0.55)
        axis.plot(
            x, planned, marker="o", linewidth=2.4,
            label="Geplante Trips", color="#00695C",
        )
        axis.plot(
            x, observed, marker="o", linewidth=2.2,
            label="Trips im Feed (inkl. NaN-Delay)", color="#1976D2",
        )
        axis.plot(
            x, observed_with_delay, marker="o", linewidth=2.2,
            label="Trips im Feed (mit Delay)", color="#8B0000",
        )
        axis.set_xticks(x)
        axis.set_xticklabels(
            report["period_start"].dt.strftime("%d.%m.%Y"),
        )
        axis.set_ylabel("Anzahl Fahrten")
        axis.set_title(
            "VOLLSTÄNDIGKEIT DER MÜNCHNER FAHRTEN - REALTIME-FEED",
            fontsize=14,
            fontweight="bold",
            color="#263238",
            pad=22,
        )
        axis.tick_params(axis="both", colors="#546E7A")
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.spines["bottom"].set_color("#CFD8DC")
        axis.legend(frameon=False)
        axis.grid(axis="y", color="#E0E6ED", linewidth=0.8)
        axis.set_axisbelow(True)
    figure.tight_layout()
    figure.savefig(
        output_path,
        dpi=120,
        bbox_inches="tight",
        facecolor=figure.get_facecolor(),
    )
    plt.close(figure)


def plot_line_completeness(
    report: pd.DataFrame,
    output_path: Path = LINE_COMPLETENESS_PLOT_PATH,
) -> None:
    """Plot the lines with the most missing trip instances."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(11, 7))
    if report.empty:
        axis.text(0.5, 0.5, "Keine Realtime-Daten vorhanden", ha="center")
        axis.set_axis_off()
    else:
        summary = (
            report.groupby("line", as_index=False)["missing_trips"]
            .sum()
            .sort_values("missing_trips", ascending=True)
            .tail(20)
        )
        axis.barh(summary["line"], summary["missing_trips"], color="#e07a5f")
        axis.set_xlabel("Fehlende Fahrten")
        axis.set_ylabel("Linie")
        axis.set_title("Fehlende Münchner Fahrten nach Linie")
        axis.grid(axis="x", alpha=0.2)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def _resume_report(
    report_path: Path,
    period_start_column: str = "period_start",
) -> tuple[pd.DataFrame | None, datetime | None]:
    """Load an existing report and split off its last (possibly partial) period.

    Returns the rows before the last period (kept as-is) and the period_start
    to resume computation from, so that partial period gets recalculated with
    any observations that arrived since the previous run.
    """
    if not report_path.exists():
        return None, None
    existing = pd.read_csv(report_path)
    if existing.empty:
        return None, None
    period_starts = pd.to_datetime(existing[period_start_column])
    last_period_start = period_starts.max()
    kept = existing.loc[period_starts < last_period_start]
    return kept, last_period_start.to_pydatetime()


def run_data_completeness_check(
    realtime_path: str = "data/realtime/mvv_realtime.parquet",
    static_data_directory: Path = Path("data/static"),
    output_path: Path = COMPLETENESS_PATH,
    plot_path: Path = COMPLETENESS_PLOT_PATH,
) -> pd.DataFrame:
    """Create and save the current completeness report and plot.

    Only periods after the last saved run are recalculated; older periods
    are kept as-is.
    """
    logger.info("Loading existing realtime data for completeness check...")
    realtime_data = load_existing_realtime_data(realtime_path)
    logger.info("Loaded %d realtime observations.", len(realtime_data))

    kept_report, resume_from = _resume_report(output_path)
    if resume_from:
        logger.info("Resuming trip completeness report from %s.", resume_from)
    else:
        logger.info("Building trip completeness report from scratch.")
    new_report = build_completeness_report(
        realtime_data,
        static_data_directory,
        start_from=resume_from,
    )
    report = (
        pd.concat([kept_report, new_report], ignore_index=True)
        if kept_report is not None and not kept_report.empty
        else new_report
    )
    logger.info("Trip completeness report: %d new period(s).", len(new_report))

    kept_line_report, line_resume_from = _resume_report(LINE_COMPLETENESS_PATH)
    if line_resume_from:
        logger.info(
            "Resuming line completeness report from %s.", line_resume_from
        )
    else:
        logger.info("Building line completeness report from scratch.")
    new_line_report = build_line_completeness_report(
        realtime_data,
        static_data_directory,
        start_from=line_resume_from,
    )
    line_report = (
        pd.concat([kept_line_report, new_line_report], ignore_index=True)
        if kept_line_report is not None and not kept_line_report.empty
        else new_line_report
    )
    logger.info(
        "Line completeness report: %d new row(s).", len(new_line_report)
    )

    save_completeness_report(report, output_path)
    save_completeness_report(line_report, LINE_COMPLETENESS_PATH)
    plot_completeness(report, plot_path)
    logger.info("Saved %s and %s.", output_path, plot_path)
    return report