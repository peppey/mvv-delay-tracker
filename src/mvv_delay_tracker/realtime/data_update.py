import pandas as pd
from pathlib import Path

from mvv_delay_tracker.realtime.data_loading import compute_is_prediction


def load_existing_realtime_data(
    parquet_path: str = "data/realtime/mvv_realtime.parquet",
    agency_path: str = "data/static/agency.txt",
) -> pd.DataFrame:
    """
    Load existing MVV real-time data from a Parquet file.

    Converts numeric GTFS-RT enum values in the relationship
    columns to their string names.
    """

    try:
        existing_df = pd.read_parquet(parquet_path)

        if "agency_name" not in existing_df.columns:
            existing_df["agency_name"] = pd.NA

        agency_file = Path(agency_path)
        if agency_file.exists() and "agency_id" in existing_df.columns:
            agency_df = pd.read_csv(
                agency_file,
                dtype={"agency_id": str},
                usecols=["agency_id", "agency_name"],
            )
            agency_names = agency_df.set_index("agency_id")["agency_name"]
            existing_df["agency_name"] = (
                existing_df["agency_id"].astype(str).map(agency_names)
                .fillna(existing_df["agency_name"])
            )

        # Backfill is_prediction for data saved before this column existed
        if "is_prediction" not in existing_df.columns:
            existing_df["is_prediction"] = compute_is_prediction(existing_df)
        else:
            existing_df["is_prediction"] = (
                existing_df["is_prediction"].astype(bool)
            )

        # Convert trip_schedule_relationship
        if "trip_schedule_relationship" not in existing_df.columns:
            existing_df["trip_schedule_relationship"] = pd.NA

        else:
            trip_relationship_mapping = {
                0: "SCHEDULED",
                1: "DUPLICATED",
                2: "CANCELED",
                3: "ADDED",
            }

            existing_df["trip_schedule_relationship"] = (
                existing_df["trip_schedule_relationship"]
                .map(trip_relationship_mapping)
                .fillna(
                    existing_df["trip_schedule_relationship"]
                )
                .astype("string")
            )

        # Convert stop_schedule_relationship
        if "stop_schedule_relationship" not in existing_df.columns:
            existing_df["stop_schedule_relationship"] = pd.NA

        else:
            stop_relationship_mapping = {
                0: "SCHEDULED",
                1: "SKIPPED",
                2: "NO_DATA",
            }

            existing_df["stop_schedule_relationship"] = (
                existing_df["stop_schedule_relationship"]
                .map(stop_relationship_mapping)
                .fillna(
                    existing_df["stop_schedule_relationship"]
                )
                .astype("string")
            )

        return existing_df

    except FileNotFoundError:
        return pd.DataFrame(
            columns=[
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
        )


def update_realtime_data(
    existing_df: pd.DataFrame,
    new_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add new real-time data and keep the latest
    observation for each trip and stop.
    """

    # Make sure trip_schedule_relationship exists
    if "trip_schedule_relationship" not in existing_df.columns:
        existing_df = existing_df.copy()
        existing_df["trip_schedule_relationship"] = pd.NA

    if "trip_schedule_relationship" not in new_df.columns:
        new_df = new_df.copy()
        new_df["trip_schedule_relationship"] = pd.NA

    # Make sure stop_schedule_relationship exists
    if "stop_schedule_relationship" not in existing_df.columns:
        existing_df = existing_df.copy()
        existing_df["stop_schedule_relationship"] = pd.NA

    if "stop_schedule_relationship" not in new_df.columns:
        new_df = new_df.copy()
        new_df["stop_schedule_relationship"] = pd.NA

    if "agency_name" not in existing_df.columns:
        existing_df = existing_df.copy()
        existing_df["agency_name"] = pd.NA

    if "agency_name" not in new_df.columns:
        new_df = new_df.copy()
        new_df["agency_name"] = pd.NA

    if "agency_id" not in existing_df.columns:
        existing_df = existing_df.copy()
        existing_df["agency_id"] = pd.NA

    if "agency_id" not in new_df.columns:
        new_df = new_df.copy()
        new_df["agency_id"] = pd.NA

    # Make sure is_prediction exists; treat legacy rows as confirmed
    if "is_prediction" not in existing_df.columns:
        existing_df = existing_df.copy()
        existing_df["is_prediction"] = False

    if "is_prediction" not in new_df.columns:
        new_df = new_df.copy()
        new_df["is_prediction"] = False

    existing_df = existing_df.copy()
    new_df = new_df.copy()

    # Make sure both relationship columns have the same type
    existing_df["trip_schedule_relationship"] = (
        existing_df["trip_schedule_relationship"]
        .astype("string")
    )

    new_df["trip_schedule_relationship"] = (
        new_df["trip_schedule_relationship"]
        .astype("string")
    )

    existing_df["stop_schedule_relationship"] = (
        existing_df["stop_schedule_relationship"]
        .astype("string")
    )

    new_df["stop_schedule_relationship"] = (
        new_df["stop_schedule_relationship"]
        .astype("string")
    )

    existing_df["is_prediction"] = existing_df["is_prediction"].astype(bool)
    new_df["is_prediction"] = new_df["is_prediction"].astype(bool)

    combined_df = pd.concat(
        [
            existing_df,
            new_df
        ],
        ignore_index=True
    )

    # A confirmed observation (is_prediction == False) always replaces a
    # prediction for the same trip/stop. Among observations with the same
    # is_prediction status, the most recently added one wins.
    ranked_df = combined_df.sort_values(
        "is_prediction",
        ascending=False,
        kind="stable",
    )
    kept_index = ranked_df.drop_duplicates(
        subset=[
            "trip_id",
            "start_date",
            "stop_id",
            "agency_id",
        ],
        keep="last",
    ).index

    combined_df = (
        combined_df[combined_df.index.isin(kept_index)]
        .reset_index(drop=True)
    )

    return combined_df


def save_realtime_data(
    realtime_df: pd.DataFrame,
    parquet_path: str = "data/realtime/mvv_realtime.parquet",
) -> None:
    """
    Save MVV real-time data to a Parquet file.

    Parameters
    ----------
    realtime_df : pandas.DataFrame
        MVV real-time data to save.

    parquet_path : str
        Path where the Parquet file is stored.
    """

    realtime_df.to_parquet(
        parquet_path,
        index=False
    )