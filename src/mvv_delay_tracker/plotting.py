import json

import matplotlib.pyplot as plt
import pandas as pd

from mvv_delay_tracker.geographic import wgs84_to_utm32


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

    delay_df = pd.read_parquet(parquet_path)

    return munich_map, delay_df


def calculate_average_station_delay(delay_df):
    """
    Calculate average departure delay for each station.
    """

    station_delay = (
        delay_df
        .dropna(subset=["departure_delay"])
        .groupby(
            ["stop_id", "stop_name"],
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


def load_stop_coordinates(
    stops_path="data/munich_stops.csv"
):
    """
    Load stop information and coordinates.
    """

    stops_df = pd.read_csv(stops_path)

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
    Merge station delays with stop coordinates.
    """

    station_delay_df = station_delay_df.merge(
        stops_df,
        on=[
            "stop_id",
            "stop_name"
        ],
        how="left"
    )

    station_delay_df = station_delay_df.dropna(
        subset=[
            "stop_lat",
            "stop_lon"
        ]
    )

    return station_delay_df


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
        cmap="RdYlGn_r",
        s=35,
        alpha=0.85,
    )

    return scatter


def mark_maximum_delay_station(
    ax,
    station_delay_df
):
    """
    Mark and label the station with the highest
    average delay.
    """

    maximum_delay_station = station_delay_df.loc[
        station_delay_df["delay_minutes"].idxmax()
    ]

    ax.scatter(
        maximum_delay_station["utm_x"],
        maximum_delay_station["utm_y"],
        s=120,
        facecolors="none",
        edgecolors="black",
        linewidths=2,
        zorder=3,
    )

    annotation_text = (
        f'{maximum_delay_station["stop_name"]}: '
        f'Durchschnittlich '
        f'{maximum_delay_station["delay_minutes"]:.0f} '
        f'Minuten Verspätung'
    )

    ax.annotate(
        annotation_text,
        xy=(
            maximum_delay_station["utm_x"],
            maximum_delay_station["utm_y"],
        ),
        xycoords="data",
        xytext=(
            0.5,
            1.04
        ),
        textcoords="axes fraction",
        ha="center",
        va="bottom",
        fontsize=10,
        fontweight="normal",
        arrowprops={
            "arrowstyle": "->",
            "connectionstyle": "arc3,rad=0.1",
            "linewidth": 1.5,
            "alpha": 0.45,
        },
        annotation_clip=False,
        zorder=4,
    )


def configure_munich_delay_plot(
    ax
):
    """
    Configure aspect ratio and axis visibility.
    """

    ax.set_aspect("equal")

    ax.axis("off")


def generate_plot(
    data_path="data/mvv_realtime.parquet",
    geojson_path="data/munich.geojson",
    stops_path="data/munich_stops.csv",
    output_path="docs/munich_delays.png"
):
    """
    Generate and save the Munich delay map.

    This function combines the complete plotting pipeline:
    loading data, calculating station delays, adding coordinates,
    and generating the plot.
    """

    munich_map, delay_df = load_data(
        geojson_path=geojson_path,
        parquet_path=data_path
    )

    station_delay = calculate_average_station_delay(
        delay_df
    )

    stops_df = load_stop_coordinates(
        stops_path=stops_path
    )

    station_delay = (
        merge_station_delays_with_coordinates(
            station_delay,
            stops_df
        )
    )

    station_delay = add_utm_coordinates(
        station_delay
    )

    figure, axis = plt.subplots(
        figsize=(12, 12)
    )

    figure.suptitle(
        "ÖPNV-Verspätungen in München",
        fontsize=18,
        fontweight="normal",
        y=0.98
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
        rect=[0, 0, 1, 0.94]
    )

    figure.savefig(
        output_path,
        dpi=70,
        bbox_inches="tight"
    )

    plt.close(figure)