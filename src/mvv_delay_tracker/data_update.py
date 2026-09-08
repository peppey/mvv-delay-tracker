import pandas as pd


def load_existing_realtime_data(
    parquet_path="data/mvv_realtime.parquet"
):
    """
    Load existing MVV real-time data from a Parquet file.

    If the Parquet file does not exist, return an empty DataFrame
    with the expected columns.

    Parameters
    ----------
    parquet_path : str
        Path to the existing Parquet file.

    Returns
    -------
    pandas.DataFrame
        Existing MVV real-time data or an empty DataFrame.
    """

    try:
        return pd.read_parquet(parquet_path)

    except FileNotFoundError:
        return pd.DataFrame(
            columns=[
                "observation_timestamp",
                "trip_id",
                "start_date",
                "line",
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
    existing_df,
    new_df
):
    """
    Add new real-time data and keep the latest
    observation for each trip and stop.

    Parameters
    ----------
    existing_df : pandas.DataFrame
        Previously stored MVV real-time data.

    new_df : pandas.DataFrame
        Newly retrieved MVV real-time data.

    Returns
    -------
    pandas.DataFrame
        Updated MVV real-time data.
    """

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
    realtime_df,
    parquet_path="data/mvv_realtime.parquet"
):
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