from mvv_delay_tracker.realtime.data_loading import load_new_data
from mvv_delay_tracker.realtime.data_update import (
    load_existing_realtime_data,
    update_realtime_data,
    save_realtime_data,
)
from mvv_delay_tracker.analysis.plotting import generate_plot


DATA_PATH = "data/realtime/mvv_realtime.parquet"
MAP_PLOT_PATH = "docs/munich_delays.png"
STATISTICS_PLOT_PATH = "docs/munich_delay_statistics.png"
COMPARISON_PLOT_PATH = "docs/delay_comparison.png"


def main() -> None:
    """Update realtime data and regenerate the published plots."""
    print("Loading new MVV data...")

    new_data = load_new_data()

    print(f"Loaded {len(new_data)} new observations.")

    print("Loading existing data...")

    existing_data = load_existing_realtime_data(
        DATA_PATH
    )

    print(f"Existing observations: {len(existing_data)}")

    print("Updating dataset...")

    updated_data = update_realtime_data(
        existing_data,
        new_data,
    )

    print(f"Updated observations: {len(updated_data)}")

    print("Saving dataset...")

    save_realtime_data(
        updated_data,
        DATA_PATH,
    )

    print("Generating delay plots...")

    generate_plot(
        data_path=DATA_PATH,
        map_output_path=MAP_PLOT_PATH,
        statistics_output_path=STATISTICS_PLOT_PATH,
        comparison_output_path=COMPARISON_PLOT_PATH,
    )

    print("Pipeline finished successfully.")


if __name__ == "__main__":
    main()