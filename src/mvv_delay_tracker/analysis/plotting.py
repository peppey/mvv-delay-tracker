import json
import re
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.colors import LinearSegmentedColormap
import pandas as pd

from mvv_delay_tracker.analysis.geographic import wgs84_to_utm32


# ============================================================
# LOAD DATA
# ============================================================

def load_data(
    geojson_path: str = "data/static/munich.geojson",
    parquet_path: str = "data/realtime/mvv_realtime.parquet",
) -> tuple[dict[str, Any], pd.DataFrame]:
    """
    Load Munich GeoJSON boundary data and MVV real-time data.

    Parameters
    ----------
    geojson_path : str
        Path to the Munich GeoJSON file.

    parquet_path : str
        Path to the MVV Parquet file.

    Returns
    -------
    munich_map : dict
        Munich boundary data.

    delay_df : pandas.DataFrame
        MVV real-time data.
    """

    with open(geojson_path, "r") as file:
        munich_map = json.load(file)

    delay_df = pd.read_parquet(
        parquet_path
    )

    return munich_map, delay_df


# ============================================================
# FILTER OBSERVATIONS
# ============================================================

def filter_observed_after_arrival(
    delay_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Keep observations where observation_timestamp is later than
    arrival_time.

    SKIPPED stop visits are always kept, even if arrival_time
    is missing.
    """

    df = delay_df.copy()

    df["observation_timestamp"] = pd.to_datetime(
        df["observation_timestamp"],
        errors="coerce"
    )

    df["arrival_time"] = pd.to_datetime(
        df["arrival_time"],
        errors="coerce"
    )

    skipped_mask = (
        df["stop_schedule_relationship"] == "SKIPPED"
    )

    observed_after_arrival_mask = (
        df["observation_timestamp"]
        > df["arrival_time"]
    )

    keep_mask = (
        skipped_mask
        | observed_after_arrival_mask
    )

    df = df[
        keep_mask
    ].copy()

    return df


def filter_munich_lines(
    delay_df: pd.DataFrame,
    lines_path: str = "data/static/munich_lines.csv",
    line_column: str = "line",
) -> pd.DataFrame:
    """Keep lines configured in the Munich lines list."""

    if line_column not in delay_df.columns:
        raise ValueError(
            f"Die Linien-Spalte '{line_column}' fehlt im DataFrame."
        )

    lines_df = pd.read_csv(lines_path, dtype={"line": str})

    if "line" not in lines_df.columns:
        raise ValueError(
            f"Die Linienliste '{lines_path}' benötigt eine 'line'-Spalte."
        )

    configured_lines = set(
        lines_df["line"].dropna().astype(str).str.strip()
    )
    line_names = delay_df[line_column].astype(str).str.strip()
    keep_mask = line_names.isin(configured_lines)

    return delay_df.loc[keep_mask].copy()


# ============================================================
# STATION DELAYS
# ============================================================

def calculate_average_station_delay(
    delay_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Calculate average departure delay for each station.

    Stations are grouped only by stop_name.
    """

    station_delay = (
        delay_df
        .dropna(
            subset=[
                "departure_delay",
                "stop_name"
            ]
        )
        .groupby(
            "stop_name",
            as_index=False
        )["departure_delay"]
        .mean()
    )

    station_delay["delay_minutes"] = (
        station_delay["departure_delay"] / 60
    )

    station_delay["delay_minutes"] = (
        station_delay["delay_minutes"]
        .clip(lower=0)
    )

    return station_delay


# ============================================================
# STOP COORDINATES
# ============================================================

def load_stop_coordinates(
    stops_path: str = "data/static/munich_stops.csv",
) -> pd.DataFrame:
    """
    Load stop information and coordinates.
    """

    stops_df = pd.read_csv(
        stops_path
    )

    stops_df["stop_id"] = (
        stops_df["stop_id"]
        .astype(str)
    )

    stops_df = stops_df[
        [
            "stop_id",
            "stop_name",
            "stop_lat",
            "stop_lon"
        ]
    ]

    return stops_df


def merge_station_delays_with_coordinates(
    station_delay_df: pd.DataFrame,
    stops_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge station delay data with stop coordinates.

    Since station delays are grouped only by stop_name,
    coordinates are also aggregated by stop_name.
    """

    stop_coordinates = (
        stops_df
        .dropna(
            subset=[
                "stop_name",
                "stop_lat",
                "stop_lon"
            ]
        )
        .groupby(
            "stop_name",
            as_index=False
        )[
            [
                "stop_lat",
                "stop_lon"
            ]
        ]
        .mean()
    )

    station_delay_df = station_delay_df.merge(
        stop_coordinates,
        on="stop_name",
        how="left"
    )

    station_delay_df = station_delay_df.dropna(
        subset=[
            "stop_lat",
            "stop_lon"
        ]
    )

    return station_delay_df


# ============================================================
# UTM COORDINATES
# ============================================================

def add_utm_coordinates(
    station_delay_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convert WGS84 station coordinates to UTM Zone 32N.
    """

    utm_coordinates = station_delay_df.apply(
        lambda row: wgs84_to_utm32(
            row["stop_lat"],
            row["stop_lon"]
        ),
        axis=1
    )

    station_delay_df["utm_x"] = (
        utm_coordinates.apply(
            lambda coordinate: coordinate[0]
        )
    )

    station_delay_df["utm_y"] = (
        utm_coordinates.apply(
            lambda coordinate: coordinate[1]
        )
    )

    return station_delay_df


# ============================================================
# MUNICH BOUNDARIES
# ============================================================

def plot_munich_boundaries(
    ax: Axes,
    munich_geojson: dict[str, Any],
) -> None:
    """
    Plot Munich administrative boundaries.
    """

    for geojson_feature in munich_geojson["features"]:

        geometry = geojson_feature["geometry"]
        geometry_type = geometry["type"]

        if geometry_type == "Polygon":

            polygons = [
                geometry["coordinates"]
            ]

        elif geometry_type == "MultiPolygon":

            polygons = geometry["coordinates"]

        else:

            continue

        for polygon in polygons:

            for polygon_ring in polygon:

                x_coordinates = [
                    coordinate[0]
                    for coordinate in polygon_ring
                ]

                y_coordinates = [
                    coordinate[1]
                    for coordinate in polygon_ring
                ]

                ax.plot(
                    x_coordinates,
                    y_coordinates,
                    linewidth=0.7
                )


# ============================================================
# STATION DELAY PLOT
# ============================================================

def plot_station_delays(
    ax: Axes,
    station_delay_df: pd.DataFrame,
) -> PathCollection:
    """
    Plot average station delays as a scatter plot.
    """

    scatter = ax.scatter(
        station_delay_df["utm_x"],
        station_delay_df["utm_y"],
        c=station_delay_df["delay_minutes"],
        cmap=LinearSegmentedColormap.from_list(
            "delay_green_red",
            ["#E8F5E9", "#2C7FB8", "#8B0000"],
        ),
        s=35,
        alpha=0.85,
    )

    return scatter


# ============================================================
# TOP TWO STATIONS
# ============================================================

def mark_maximum_delay_station(
    ax: Axes,
    station_delay_df: pd.DataFrame,
) -> None:
    """
    Mark and label the two stations with the highest
    average delay.

    The annotations are placed at different positions
    to avoid overlaps between text and arrows.
    """

    top_two_stations = (
        station_delay_df
        .nlargest(
            2,
            "delay_minutes"
        )
    )

    annotation_positions = [
        (0.25, 1.04),
        (0.75, 1.04)
    ]

    connection_styles = [
        "arc3,rad=0.15",
        "arc3,rad=-0.15"
    ]

    for (
        (_, station),
        (text_x, text_y),
        connection_style
    ) in zip(
        top_two_stations.iterrows(),
        annotation_positions,
        connection_styles
    ):

        # ----------------------------------------------------
        # Mark station
        # ----------------------------------------------------

        ax.scatter(
            station["utm_x"],
            station["utm_y"],
            s=120,
            facecolors="none",
            edgecolors="black",
            linewidths=2,
            zorder=3,
        )

        # ----------------------------------------------------
        # Annotation text
        # ----------------------------------------------------

        annotation_text = (
            f'{station["stop_name"]}: '
            f'Durchschnittlich '
            f'{station["delay_minutes"]:.1f} '
            f'Minuten Verspätung'
        )

        # ----------------------------------------------------
        # Annotation
        # ----------------------------------------------------

        ax.annotate(
            annotation_text,
            xy=(
                station["utm_x"],
                station["utm_y"],
            ),
            xycoords="data",
            xytext=(
                text_x,
                text_y
            ),
            textcoords="axes fraction",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="normal",
            arrowprops={
                "arrowstyle": "->",
                "connectionstyle": connection_style,
                "linewidth": 1.5,
                "alpha": 0.45,
            },
            annotation_clip=False,
            zorder=4,
            color="#546E7A"
        )


# ============================================================
# PLOT CONFIGURATION
# ============================================================

def configure_munich_delay_plot(
    ax: Axes,
) -> None:
    """
    Configure aspect ratio and axis visibility.
    """

    ax.set_aspect("equal")

    ax.axis("off")


# ============================================================
# STATISTICS
# ============================================================

def calculate_delay_statistics(
    delay_df: pd.DataFrame,
    line_column: str = "line",
    datetime_column: str = "observation_timestamp",
) -> dict[str, Any]:
    """
    Calculate key statistics for the Munich public transport
    delay report.

    NaN values in departure_delay are ignored.

    The input DataFrame is assumed to already contain only
    observations where observation_timestamp is later than
    arrival_time.
    """

    df = delay_df.copy()

    # --------------------------------------------------------
    # Check required columns
    # --------------------------------------------------------

    required_columns = [
        "departure_delay",
        "stop_name",
        line_column
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        raise ValueError(
            "Folgende benötigte Spalten fehlen: "
            f"{missing_columns}\n\n"
            f"Vorhandene Spalten:\n"
            f"{df.columns.tolist()}"
        )

    # --------------------------------------------------------
    # Remove missing delay values
    # --------------------------------------------------------

    df = df.dropna(
        subset=[
            "departure_delay"
        ]
    )

    # --------------------------------------------------------
    # Convert delay to minutes
    # --------------------------------------------------------

    df["delay_minutes"] = (
        df["departure_delay"] / 60
    ).clip(lower=0)

    # --------------------------------------------------------
    # Largest individual delay
    # --------------------------------------------------------

    maximum_delay = df.loc[
        df["delay_minutes"].idxmax()
    ]

    maximum_delay_minutes = (
        maximum_delay["delay_minutes"]
    )

    maximum_delay_station = (
        maximum_delay["stop_name"]
    )

    maximum_delay_line = (
        maximum_delay[line_column]
    )

    # --------------------------------------------------------
    # Date of maximum delay
    # --------------------------------------------------------

    maximum_delay_date = "Unbekannt"

    if datetime_column in df.columns:

        timestamp = pd.to_datetime(
            maximum_delay[datetime_column],
            errors="coerce"
        )

        if pd.notna(timestamp):

            maximum_delay_date = (
                timestamp.strftime("%d.%m.%Y")
            )

    # --------------------------------------------------------
    # Average delay overall
    # --------------------------------------------------------

    average_delay = (
        df["delay_minutes"].mean()
    )

    # --------------------------------------------------------
    # Most delayed line
    # --------------------------------------------------------

    line_statistics = (
        df
        .dropna(
            subset=[
                line_column
            ]
        )
        .groupby(
            line_column
        )["delay_minutes"]
        .mean()
        .sort_values(
            ascending=False
        )
    )

    most_delayed_line = (
        line_statistics.index[0]
    )

    most_delayed_line_delay = (
        line_statistics.iloc[0]
    )

    # --------------------------------------------------------
    # Most delayed station
    # --------------------------------------------------------

    station_statistics = (
        df
        .dropna(
            subset=[
                "stop_name"
            ]
        )
        .groupby(
            "stop_name"
        )["delay_minutes"]
        .mean()
        .sort_values(
            ascending=False
        )
    )

    most_delayed_station = (
        station_statistics.index[0]
    )

    most_delayed_station_delay = (
        station_statistics.iloc[0]
    )

    # --------------------------------------------------------
    # Percentage delayed more than 5 minutes
    # --------------------------------------------------------

    percentage_over_5_minutes = (
        (
            df["delay_minutes"] > 5
        ).mean()
        * 100
    )

    # --------------------------------------------------------
    # Number of observations
    # --------------------------------------------------------

    number_of_departures = len(df)

    # --------------------------------------------------------
    # Number of unique trips
    # --------------------------------------------------------

    trip_columns = [
        "trip_id",
        "start_date"
    ]

    available_trip_columns = [
        column
        for column in trip_columns
        if column in df.columns
    ]

    number_of_trips = (
        df[available_trip_columns]
        .drop_duplicates()
        .shape[0]
    )

    # --------------------------------------------------------
    # Percentage of skipped stop visits
    # --------------------------------------------------------

    percentage_skipped_stops = 0.0

    if "stop_schedule_relationship" in delay_df.columns:

        relevant_stop_visits = (
            delay_df[
                delay_df[
                    "stop_schedule_relationship"
                ].isin(
                    [
                        "SCHEDULED",
                        "SKIPPED"
                    ]
                )
            ]
        )

        number_of_skipped_stops = len(
            relevant_stop_visits[
                relevant_stop_visits[
                    "stop_schedule_relationship"
                ] == "SKIPPED"
            ].index
        )

        number_of_relevant_stops = (
            len(
                relevant_stop_visits
            )
        )

        if number_of_relevant_stops > 0:

            percentage_skipped_stops = (
                number_of_skipped_stops
                / number_of_relevant_stops
                * 100
            )

    # --------------------------------------------------------
    # Number of lines
    # --------------------------------------------------------

    number_of_lines = (
        df[line_column].nunique()
    )

    # --------------------------------------------------------
    # Number of stations
    # --------------------------------------------------------

    number_of_stations = (
        df["stop_name"].nunique()
    )

    return {
        "maximum_delay_minutes":
            maximum_delay_minutes,

        "maximum_delay_station":
            maximum_delay_station,

        "maximum_delay_line":
            maximum_delay_line,

        "maximum_delay_date":
            maximum_delay_date,

        "average_delay_minutes":
            average_delay,

        "most_delayed_line":
            most_delayed_line,

        "most_delayed_line_delay":
            most_delayed_line_delay,

        "most_delayed_station":
            most_delayed_station,

        "most_delayed_station_delay":
            most_delayed_station_delay,

        "percentage_over_5_minutes":
            percentage_over_5_minutes,

        "percentage_skipped_stops":
            percentage_skipped_stops,

        "number_of_departures":
            number_of_departures,

        "number_of_trips":
            number_of_trips,

        "number_of_lines":
            number_of_lines,

        "number_of_stations":
            number_of_stations,
    }


def classify_transport_mode(line_name: str) -> str | None:
    """
    Classify an MVV line as S-Bahn, U-Bahn, or Tram/Bus.
    """

    normalized_line_name = str(line_name).strip().upper()

    if re.fullmatch(r"S[A-Z0-9]{1,2}", normalized_line_name):
        return "S-Bahn"

    if re.fullmatch(r"U[A-Z0-9]{1,2}", normalized_line_name):
        return "U-Bahn"

    if (
        re.fullmatch(r"\d+", normalized_line_name)
        or normalized_line_name.startswith(("X", "N"))
    ):
        return "Tram/Bus"

    return None


def calculate_transport_mode_delays(
    delay_df: pd.DataFrame,
    line_column: str = "line",
    lines_path: str = "data/static/munich_lines.csv",
) -> pd.DataFrame:
    """
    Calculate average departure delays for each transport mode.
    """

    classified_delay_df = delay_df.copy()
    lines_df = pd.read_csv(lines_path, dtype={"line": str})
    line_modes = lines_df.set_index("line")["mode"]
    classified_delay_df["transport_mode"] = (
        classified_delay_df[line_column].astype(str).str.strip().map(line_modes)
    )
    classified_delay_df["transport_mode"] = (
        classified_delay_df["transport_mode"]
        .replace({"Tram": "Tram/Bus", "Bus": "Tram/Bus"})
        .fillna(
            classified_delay_df[line_column].map(classify_transport_mode)
        )
    )

    classified_delay_df = classified_delay_df.dropna(
        subset=["transport_mode", "departure_delay"]
    )
    classified_delay_df["delay_minutes"] = (
        classified_delay_df["departure_delay"] / 60
    ).clip(lower=0)

    transport_mode_order = ["S-Bahn", "U-Bahn", "Tram/Bus"]

    return (
        classified_delay_df
        .groupby("transport_mode", as_index=False)
        .agg(
            delay_minutes=("delay_minutes", "mean"),
            number_of_observations=("delay_minutes", "size"),
        )
        .set_index("transport_mode")
        .reindex(transport_mode_order)
        .reset_index()
    )


def create_delay_comparison_plot(
    delay_df: pd.DataFrame,
    output_path: str = "docs/delay_comparison.png",
    line_column: str = "line",
    lines_path: str = "data/static/munich_lines.csv",
) -> None:
    """
    Create a bar chart comparing average delays by transport mode.
    """

    transport_mode_delays = calculate_transport_mode_delays(
        delay_df,
        line_column=line_column,
        lines_path=lines_path,
    )
    figure, axis = plt.subplots(figsize=(10, 6))

    figure.patch.set_facecolor("#FFFFFF")
    axis.set_facecolor("#FFFFFF")

    bar_colors = ["#00695C", "#1976D2", "#00897B"]
    bars = axis.bar(
        transport_mode_delays["transport_mode"],
        transport_mode_delays["delay_minutes"].fillna(0),
        color=bar_colors,
        width=0.58,
    )

    axis.set_title(
        "ÖPNV VERSPÄTUNGEN NACH VERKEHRSMITTEL - MÜNCHEN 2026" ,
        fontsize=14,
        fontweight="bold",
        color="#263238",
        pad=22,
    )
    axis.set_ylabel(
        "Durchschnittliche Verspätung [Minuten]",
        color="#546E7A",
    )
    axis.tick_params(axis="both", colors="#546E7A")
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.spines["bottom"].set_color("#CFD8DC")
    axis.grid(axis="y", color="#E0E6ED", linewidth=0.8)
    axis.set_axisbelow(True)

    maximum_delay = transport_mode_delays["delay_minutes"].max()
    axis.set_ylim(0, max(1, maximum_delay * 1.2))

    for bar, delay_minutes, number_of_observations in zip(
        bars,
        transport_mode_delays["delay_minutes"],
        transport_mode_delays["number_of_observations"],
    ):
        label = "Keine Daten" if pd.isna(delay_minutes) else (
            f"{delay_minutes:.1f} min · n={int(number_of_observations):,}"
        )
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            0 if pd.isna(delay_minutes) else bar.get_height() + 0.05,
            label,
            ha="center",
            va="bottom",
            color="#546E7A",
            fontsize=11,
            fontweight="bold",
        )

    figure.text(
        0.5,
        0.015,
        "n = Anzahl erfasster Haltestellenbesuche",
        ha="center",
        va="center",
        fontsize=9,
        color="#90A4AE",
    )

    figure.tight_layout(rect=[0, 0.04, 1, 1])
    figure.savefig(
        output_path,
        dpi=120,
        bbox_inches="tight",
        facecolor=figure.get_facecolor(),
    )
    plt.close(figure)


def create_line_comparison_plot(
    delay_df: pd.DataFrame,
    output_path: str = "docs/line_comparison.png",
    line_column: str = "line",
    lines_path: str = "data/static/munich_lines.csv",
    number_of_lines: int = 15,
) -> None:
    """Create a horizontal plot of the lines with the highest median delay."""

    lines_df = pd.read_csv(lines_path, dtype={"line": str})
    line_modes = lines_df.set_index("line")["mode"]

    line_delay_df = delay_df.copy()
    line_delay_df["transport_mode"] = (
        line_delay_df[line_column].astype(str).str.strip().map(line_modes)
    )
    line_delay_df["transport_mode"] = (
        line_delay_df["transport_mode"]
        .replace({"Tram": "Tram/Bus", "Bus": "Tram/Bus"})
        .fillna(line_delay_df[line_column].map(classify_transport_mode))
    )
    line_delay_df = line_delay_df.dropna(
        subset=[line_column, "transport_mode", "departure_delay"]
    )
    line_delay_df["delay_minutes"] = (
        line_delay_df["departure_delay"] / 60
    ).clip(lower=0)

    line_statistics = (
        line_delay_df
        .groupby([line_column, "transport_mode"], as_index=False)
        .agg(
            median_delay=("delay_minutes", "median"),
            number_of_observations=("delay_minutes", "size"),
        )
        .sort_values("median_delay", ascending=False)
        .head(number_of_lines)
        .sort_values("median_delay")
    )

    mode_colors = {
        "S-Bahn": "#00695C",
        "U-Bahn": "#1976D2",
        "Tram/Bus": "#00897B",
    }

    figure, axis = plt.subplots(figsize=(11, 8))
    figure.patch.set_facecolor("#FFFFFF")
    axis.set_facecolor("#FFFFFF")

    bars = axis.barh(
        line_statistics[line_column].astype(str),
        line_statistics["median_delay"],
        color=line_statistics["transport_mode"].map(mode_colors),
        height=0.62,
    )

    axis.set_title(
        "MEDIANE VERSPÄTUNG NACH LINIE - MÜNCHEN 2026",
        fontsize=14,
        fontweight="bold",
        color="#263238",
        pad=22,
    )
    axis.set_xlabel("Mediane Verspätung [Minuten]", color="#546E7A")
    axis.tick_params(axis="both", colors="#546E7A")
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.spines["bottom"].set_color("#CFD8DC")
    axis.grid(axis="x", color="#E0E6ED", linewidth=0.8)
    axis.set_axisbelow(True)

    maximum_delay = line_statistics["median_delay"].max()
    axis.set_xlim(0, max(1, maximum_delay * 1.3))

    for bar, (_, line) in zip(bars, line_statistics.iterrows()):
        axis.text(
            bar.get_width() + maximum_delay * 0.02,
            bar.get_y() + bar.get_height() / 2,
            f'{line["median_delay"]:.1f} min · n={line["number_of_observations"]:,}',
            va="center",
            color="#546E7A",
            fontsize=10,
        )

    figure.text(
        0.5,
        0.015,
        "n = Anzahl erfasster Haltestellenbesuche",
        ha="center",
        va="center",
        fontsize=9,
        color="#90A4AE",
    )

    figure.tight_layout(rect=[0, 0.04, 1, 1])
    figure.savefig(
        output_path,
        dpi=120,
        bbox_inches="tight",
        facecolor=figure.get_facecolor(),
    )
    plt.close(figure)


def create_delay_heatmap(
    delay_df: pd.DataFrame,
    output_path: str = "docs/delay_heatmap.png",
) -> None:
    """Create a weekday-by-hour heatmap of average departure delays."""

    required_columns = [
        "observation_timestamp",
        "departure_delay",
    ]
    missing_columns = [
        column
        for column in required_columns
        if column not in delay_df.columns
    ]
    if missing_columns:
        raise ValueError(
            f"Für die Heatmap fehlen Spalten: {missing_columns}"
        )

    heatmap_df = delay_df[required_columns].copy()
    heatmap_df["observation_timestamp"] = pd.to_datetime(
        heatmap_df["observation_timestamp"],
        errors="coerce",
    )
    heatmap_df["delay_minutes"] = (
        pd.to_numeric(heatmap_df["departure_delay"], errors="coerce") / 60
    ).clip(lower=0)
    heatmap_df = heatmap_df.dropna(
        subset=["observation_timestamp", "delay_minutes"]
    )
    heatmap_df["weekday"] = heatmap_df[
        "observation_timestamp"
    ].dt.dayofweek
    heatmap_df["hour"] = heatmap_df[
        "observation_timestamp"
    ].dt.hour

    weekday_order = [
        "Montag",
        "Dienstag",
        "Mittwoch",
        "Donnerstag",
        "Freitag",
        "Samstag",
        "Sonntag",
    ]
    heatmap_values = (
        heatmap_df
        .pivot_table(
            index="weekday",
            columns="hour",
            values="delay_minutes",
            aggfunc="mean",
        )
        .reindex(index=range(7), columns=range(24))
    )

    delay_colormap = LinearSegmentedColormap.from_list(
        "delay_green_blue_red",
        ["#E8F5E9", "#2C7FB8", "#8B0000"],
    )
    maximum_delay = heatmap_values.to_numpy().max()

    number_of_observations = len(heatmap_df)

    figure, axis = plt.subplots(figsize=(15, 6.5))
    figure.patch.set_facecolor("#FFFFFF")
    axis.set_facecolor("#FFFFFF")

    image = axis.imshow(
        heatmap_values,
        cmap=delay_colormap,
        aspect="auto",
        interpolation="nearest",
        vmin=0,
        vmax=max(1, maximum_delay),
    )
    displayed_hours = range(0, 24, 2)
    axis.set_xticks(list(displayed_hours))
    axis.set_xticklabels(
        [f"{hour:02d}:00" for hour in displayed_hours],
        fontsize=10,
    )
    axis.set_yticks(range(7))
    axis.set_yticklabels(weekday_order)
    axis.set_xlabel("Uhrzeit", color="#546E7A")
    axis.set_ylabel("Wochentag", color="#546E7A")
    axis.tick_params(axis="both", colors="#546E7A")
    axis.set_title(
        "DURCHSCHNITTLICHE VERSPÄTUNG NACH WOCHENTAG UND UHRZEIT",
        fontsize=14,
        fontweight="bold",
        color="#263238",
        pad=18,
    )
    axis.spines[:].set_visible(False)

    colorbar = figure.colorbar(image, ax=axis, pad=0.02)
    colorbar.set_label("Durchschnittliche Verspätung [Minuten]")
    colorbar.ax.tick_params(colors="#546E7A")

    figure.text(
        0.5,
        0.015,
        f"Leere Felder: keine Beobachtungen · Datenbasis: "
        f"{number_of_observations:,} erfasste Haltestellenbesuche",
        ha="center",
        va="center",
        fontsize=9,
        color="#90A4AE",
    )
    figure.tight_layout(rect=[0, 0.04, 1, 1])
    figure.savefig(
        output_path,
        dpi=120,
        bbox_inches="tight",
        facecolor=figure.get_facecolor(),
    )
    plt.close(figure)


# ============================================================
# STATISTICS REPORT
# ============================================================

def create_delay_statistics_plot(
    statistics: dict[str, Any],
    output_path: str = "docs/munich_delay_statistics.png",
) -> None:
    """
    Create a colorful PNG containing key Munich public
    transport delay statistics.
    """

    figure, axis = plt.subplots(
        figsize=(14, 9)
    )

    figure.patch.set_facecolor(
        "#FFFFFF"
    )

    axis.set_facecolor(
        "#FFFFFF"
    )

    axis.axis("off")

    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    figure.text(
        0.5,
        0.94,
        "ÖPNV VERSPÄTUNGEN - MÜNCHEN 2026",
        ha="center",
        va="center",
        fontsize=24,
        fontweight="bold",
        color="#263238"
    )

    figure.text(
        0.5,
        0.895,
        "Kennzahlen zu Verspätungen im Münchner ÖPNV",
        ha="center",
        va="center",
        fontsize=12,
        color="#546E7A"
    )

    # --------------------------------------------------------
    # KPI helper
    # --------------------------------------------------------

    def add_kpi(
        x: float,
        y: float,
        title: str,
        value: str,
        description: str = "",
        accent_color: str = "#1976D2",
        value_size: int = 25,
    ) -> None:
        """
        Add one colored KPI card.
        """

        axis.text(
            x,
            y,
            "",
            transform=axis.transAxes,
            ha="center",
            va="center",
            fontsize=1,
            bbox=dict(
                boxstyle="round,pad=1.5",
                facecolor="white",
                edgecolor="#E0E6ED",
                linewidth=1.2
            )
        )

        axis.plot(
            [
                x - 0.15,
                x + 0.15
            ],
            [
                y + 0.075,
                y + 0.075
            ],
            transform=axis.transAxes,
            linewidth=5,
            solid_capstyle="round",
            color=accent_color,
            clip_on=False
        )

        axis.text(
            x,
            y + 0.025,
            title,
            transform=axis.transAxes,
            ha="center",
            va="center",
            fontsize=11,
            color="#546E7A"
        )

        axis.text(
            x,
            y - 0.035,
            value,
            transform=axis.transAxes,
            ha="center",
            va="center",
            fontsize=value_size,
            fontweight="bold",
            color=accent_color
        )

        if description:

            axis.text(
                x,
                y - 0.09,
                description,
                transform=axis.transAxes,
                ha="center",
                va="center",
                fontsize=9.5,
                color="#78909C"
            )

    # ========================================================
    # ROW 1
    # ========================================================

    add_kpi(
        0.27,
        0.72,
        "GRÖSSTE VERSPÄTUNG",
        (
            f'{statistics["maximum_delay_minutes"]:.1f} min'
        ),
        (
            f'{statistics["maximum_delay_station"]} · '
            f'{statistics["maximum_delay_line"]} · '
            f'{statistics["maximum_delay_date"]}'
        ),
        accent_color="#00695C",
        value_size=27
    )

    add_kpi(
        0.73,
        0.72,
        "VERSPÄTETSTE LINIE",
        (
            f'{statistics["most_delayed_line"]}'
        ),
        (
            f'Ø {statistics["most_delayed_line_delay"]:.1f} min '
            f'Verspätung'
        ),
        accent_color="#1976D2",
        value_size=27
    )

    # ========================================================
    # ROW 2
    # ========================================================

    add_kpi(
        0.27,
        0.46,
        "VERSPÄTETSTE STATION",
        (
            f'{statistics["most_delayed_station"]}'
        ),
        (
            f'Ø {statistics["most_delayed_station_delay"]:.1f} min'
        ),
        accent_color="#00897B",
        value_size=21
    )

    add_kpi(
        0.73,
        0.46,
        "DURCHSCHNITTLICHE VERSPÄTUNG",
        (
            f'{statistics["average_delay_minutes"]:.1f} min'
        ),
        "über alle Abfahrten",
        accent_color="#1976D2",
        value_size=27
    )

    # ========================================================
    # ROW 3
    # ========================================================

    add_kpi(
        0.27,
        0.20,
        "ABFAHRTEN > 5 MIN VERSPÄTET",
        (
            f'{statistics["percentage_over_5_minutes"]:.1f} %'
        ),
        "aller erfassten Abfahrten",
        accent_color="#00897B",
        value_size=27
    )

    add_kpi(
        0.73,
        0.20,
        "ÜBERSPRUNGENE HALTESTELLENBESUCHE",
        (
            f'{statistics["percentage_skipped_stops"]:.1f} %'
        ),
        "aller Haltestellenbesuche",
        accent_color="#00695C",
        value_size=25
    )

    # --------------------------------------------------------
    # Footer
    # --------------------------------------------------------

    figure.text(
        0.5,
        0.035,
        f'Datenbasis: {statistics["number_of_trips"]:,} Fahrten seit dem 11.9.2026',
        ha="center",
        va="center",
        fontsize=9,
        color="#90A4AE"
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    figure.savefig(
        output_path,
        dpi=120,
        bbox_inches="tight",
        facecolor=figure.get_facecolor()
    )

    plt.close(figure)


# ============================================================
# MAIN FUNCTION
# ============================================================

def generate_plot(
    data_path: str = "data/realtime/mvv_realtime.parquet",
    geojson_path: str = "data/static/munich.geojson",
    stops_path: str = "data/static/munich_stops.csv",
    lines_path: str = "data/static/munich_lines.csv",
    map_output_path: str = "docs/munich_delays.png",
    statistics_output_path: str = "docs/munich_delay_statistics.png",
    comparison_output_path: str = "docs/delay_comparison.png",
    line_comparison_output_path: str = "docs/line_comparison.png",
    heatmap_output_path: str = "docs/delay_heatmap.png",
    line_column: str = "line",
) -> None:
    """
    Generate and save the Munich delay map and statistics report.

    Only observations where observation_timestamp is later than
    arrival_time are included in the analysis.
    """

    # ========================================================
    # Load data
    # ========================================================

    munich_map, delay_df = load_data(
        geojson_path=geojson_path,
        parquet_path=data_path
    )

    # ========================================================
    # Filter observations
    # ========================================================

    original_number_of_rows = len(
        delay_df
    )

    delay_df = filter_observed_after_arrival(
        delay_df
    )

    delay_df = filter_munich_lines(
        delay_df,
        lines_path=lines_path,
        line_column=line_column,
    )

    print(
        f"Originale Beobachtungen: "
        f"{original_number_of_rows:,}"
    )

    print(
        f"Beobachtungen nach Filter: "
        f"{len(delay_df):,}"
    )

    # ========================================================
    # Calculate statistics
    # ========================================================

    statistics = calculate_delay_statistics(
        delay_df,
        line_column=line_column,
        datetime_column="observation_timestamp"
    )

    # ========================================================
    # Calculate station delays
    # ========================================================

    station_delay = calculate_average_station_delay(
        delay_df
    )

    # ========================================================
    # Load station coordinates
    # ========================================================

    stops_df = load_stop_coordinates(
        stops_path=stops_path
    )

    # ========================================================
    # Merge delays with coordinates
    # ========================================================

    station_delay = (
        merge_station_delays_with_coordinates(
            station_delay,
            stops_df
        )
    )

    # ========================================================
    # Convert coordinates
    # ========================================================

    station_delay = add_utm_coordinates(
        station_delay
    )

    # ========================================================
    # Create Munich map
    # ========================================================

    figure, axis = plt.subplots(
        figsize=(12, 12)
    )

    figure.text(
        0.5,
        0.94,
        "ÖPNV VERSPÄTUNGEN - MÜNCHEN 2026",
        ha="center",
        va="center",
        fontsize=24,
        fontweight="bold",
        color="#263238"
    )

    figure.text(
        0.02,
        0.5,
        f'Datenbasis: {statistics["number_of_trips"]:,} Fahrten seit dem 9.9.26',
        ha="center",
        va="center",
        fontsize=9,
        color="#546E7A",
        rotation=90,
    )

    plot_munich_boundaries(
        axis,
        munich_map
    )

    scatter = plot_station_delays(
        axis,
        station_delay
    )

    mark_maximum_delay_station(
        axis,
        station_delay
    )

    colorbar = figure.colorbar(
        scatter,
        ax=axis,
        orientation="horizontal",
        fraction=0.035,
        pad=0.04
    )

    colorbar.set_label(
        "Durchschnittliche Verspätung [Minuten]"
    )

    configure_munich_delay_plot(
        axis
    )

    figure.tight_layout(
        rect=[
            0,
            0,
            1,
            0.94
        ]
    )

    figure.savefig(
        map_output_path,
        dpi=70,
        bbox_inches="tight"
    )

    plt.close(figure)

    # ========================================================
    # Create statistics report
    # ========================================================

    create_delay_statistics_plot(
        statistics,
        output_path=statistics_output_path
    )

    create_delay_comparison_plot(
        delay_df,
        output_path=comparison_output_path,
        line_column=line_column,
        lines_path=lines_path,
    )

    create_line_comparison_plot(
        delay_df,
        output_path=line_comparison_output_path,
        line_column=line_column,
        lines_path=lines_path,
    )

    create_delay_heatmap(
        delay_df,
        output_path=heatmap_output_path,
    )

    # ========================================================
    # Print output paths
    # ========================================================

    print(
        f"Map gespeichert unter: "
        f"{map_output_path}"
    )

    print(
        f"Statistik-Report gespeichert unter: "
        f"{statistics_output_path}"
    )


def main() -> None:
    """Generate all delay plots using the default project paths."""
    generate_plot()


if __name__ == "__main__":
    main()
