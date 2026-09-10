import pandas as pd


def load_existing_realtime_data(
    parquet_path: str = "data/realtime/mvv_realtime.parquet",
) -> pd.DataFrame:
    """
    Load existing MVV real-time data from a Parquet file.

    Converts numeric GTFS-RT enum values in the relationship
    columns to their string names.
    """

    try:
        existing_df = pd.read_parquet(parquet_path)

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
                "stop_id",
                "stop_name",
                "stop_sequence",
                "departure_time",
                "departure_delay",
                "arrival_time",
                "arrival_delay",
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

    combined_df = pd.concat(
        [
            existing_df,
            new_df
        ],
        ignore_index=True
    )

    combined_df = (
        combined_df
        .drop_duplicates(
            subset=[
                "trip_id",
                "start_date",
                "stop_id"
            ],
            keep="last"
        )
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