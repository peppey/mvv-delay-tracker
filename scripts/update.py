from mvv_delay_tracker.data_loading import load_new_data
from mvv_delay_tracker.data_update import (
    load_existing_realtime_data,
    update_realtime_data,
    save_realtime_data,
)
from mvv_delay_tracker.plotting import generate_plot


DATA_PATH = "data/mvv_realtime.parquet"
PLOT_PATH = "docs/munich_delays.png"


def main():
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

    save_realtime_data(
        updated_data,
        DATA_PATH,
    )

    print("Generating delay map...")

    generate_plot(
        data_path=DATA_PATH,
        output_path=PLOT_PATH,
    )

    print("Pipeline finished successfully.")


if __name__ == "__main__":
    main()