import json

import matplotlib.pyplot as plt
import pandas as pd

from mvv_delay_tracker.geographic import wgs84_to_utm32


# ============================================================
# LOAD DATA
# ============================================================

def load_data(
    geojson_path="data/munich.geojson",
    parquet_path="data/mvv_realtime.parquet"
):
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
    delay_df
):
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


# ============================================================
# STATION DELAYS
# ============================================================

def calculate_average_station_delay(
    delay_df
):
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
    stops_path="data/munich_stops.csv"
):
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
    station_delay_df,
    stops_df
):
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
    station_delay_df
):
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
    ax,
    munich_geojson
):
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
    ax,
    station_delay_df
):
    """
    Plot average station delays as a scatter plot.
    """

    scatter = ax.scatter(
        station_delay_df["utm_x"],
        station_delay_df["utm_y"],
        c=station_delay_df["delay_minutes"],
        cmap="PuBuGn",
        s=35,
        alpha=0.85,
    )

    return scatter


# ============================================================
# TOP TWO STATIONS
# ============================================================

def mark_maximum_delay_station(
    ax,
    station_delay_df
):
    """
    Mark and label the two stations with the highest
    average delay.
    """

    top_two_stations = (
        station_delay_df
        .nlargest(
            2,
            "delay_minutes"
        )
    )

    annotation_positions = [
        (0.5, 1.04),
        (0.5, 0.98)
    ]

    for (_, station), (text_x, text_y) in zip(
        top_two_stations.iterrows(),
        annotation_positions
    ):

        ax.scatter(
            station["utm_x"],
            station["utm_y"],
            s=120,
            facecolors="none",
            edgecolors="black",
            linewidths=2,
            zorder=3,
        )

        annotation_text = (
            f'{station["stop_name"]}: '
            f'Durchschnittlich '
            f'{station["delay_minutes"]:.1f} '
            f'Minuten Verspätung'
        )

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
                "connectionstyle": "arc3,rad=0.1",
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
    ax
):
    """
    Configure aspect ratio and axis visibility.
    """

    ax.set_aspect("equal")

    ax.axis("off")


# ============================================================
# STATISTICS
# ============================================================

def calculate_delay_statistics(
    delay_df,
    line_column="line",
    datetime_column="observation_timestamp"
):
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


# ============================================================
# STATISTICS REPORT
# ============================================================

def create_delay_statistics_plot(
    statistics,
    output_path="docs/munich_delay_statistics.png"
):
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
        "MVV VERSPÄTUNGEN 2026",
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
        x,
        y,
        title,
        value,
        description="",
        accent_color="#1976D2",
        value_size=25
    ):
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
        f'Datenbasis: {statistics["number_of_trips"]:,} Fahrten seit dem 8.9.26',
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
    data_path="data/mvv_realtime.parquet",
    geojson_path="data/munich.geojson",
    stops_path="data/munich_stops.csv",
    map_output_path="docs/munich_delays.png",
    statistics_output_path="docs/munich_delay_statistics.png",
    line_column="line"
):
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
        "MVV VERSPÄTUNGEN 2026",
        ha="center",
        va="center",
        fontsize=24,
        fontweight="bold",
        color="#263238"
    )

    figure.text(
        0.02,
        0.5,
        f'Datenbasis: {statistics["number_of_trips"]:,} Fahrten seit dem 8.9.26',
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
