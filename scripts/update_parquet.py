import logging

from mvv_delay_tracker.realtime.data_loading import load_new_data
from mvv_delay_tracker.realtime.data_update import (
    load_existing_realtime_data,
    update_realtime_data,
    save_realtime_data,
)
from mvv_delay_tracker.analysis.plotting import generate_plot


logger = logging.getLogger(__name__)

DATA_PATH = "data/realtime/mvv_realtime.parquet"
MAP_PLOT_PATH = "docs/munich_delays.png"
STATISTICS_PLOT_PATH = "docs/munich_delay_statistics.png"
COMPARISON_PLOT_PATH = "docs/delay_comparison.png"


def main() -> None:
    """Update realtime data and regenerate the published plots."""
    logger.info("Loading new MVV data...")

    new_data = load_new_data()

    logger.info("Loaded %d new observations.", len(new_data))

    logger.info("Loading existing data...")

    existing_data = load_existing_realtime_data(
        DATA_PATH
    )

    logger.info("Existing observations: %d", len(existing_data))

    logger.info("Updating dataset...")

    updated_data = update_realtime_data(
        existing_data,
        new_data,
    )

    logger.info("Updated observations: %d", len(updated_data))

    logger.info("Saving dataset...")

    save_realtime_data(
        updated_data,
        DATA_PATH,
    )

    logger.info("Generating delay plots...")

    generate_plot(
        data_path=DATA_PATH,
        map_output_path=MAP_PLOT_PATH,
        statistics_output_path=STATISTICS_PLOT_PATH,
        comparison_output_path=COMPARISON_PLOT_PATH,
    )

    logger.info("Pipeline finished successfully.")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    main()