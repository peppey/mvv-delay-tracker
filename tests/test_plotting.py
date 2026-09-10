import pandas as pd

from mvv_delay_tracker.analysis.plotting import (
    calculate_average_station_delay,
    calculate_delay_statistics,
    calculate_transport_mode_delays,
    classify_transport_mode,
    create_delay_comparison_plot,
)


def test_classify_transport_mode():
    assert classify_transport_mode("S1") == "S-Bahn"
    assert classify_transport_mode("U12") == "U-Bahn"
    assert classify_transport_mode("18") == "Tram/Bus"
    assert classify_transport_mode("X30") == "Tram/Bus"
    assert classify_transport_mode("N40") == "Tram/Bus"
    assert classify_transport_mode("RE1") is None


def test_calculate_transport_mode_delays():
    delay_df = pd.DataFrame({
        "line": ["S1", "U12", "18", "X30", "S2"],
        "departure_delay": [60, 120, 180, 240, -60],
    })

    result = calculate_transport_mode_delays(delay_df)

    assert list(result["transport_mode"]) == [
        "S-Bahn",
        "U-Bahn",
        "Tram/Bus",
    ]
    assert list(result["delay_minutes"]) == [1.0, 2.0, 3.5]


def test_average_delays_exclude_early_departures():
    delay_df = pd.DataFrame({
        "stop_name": ["Central", "Central"],
        "line": ["S1", "S1"],
        "departure_delay": [60, -60],
    })

    station_result = calculate_average_station_delay(delay_df)

    statistics_result = calculate_delay_statistics(delay_df)

    assert station_result.iloc[0]["delay_minutes"] == 1.0
    assert statistics_result["average_delay_minutes"] == 1.0


def test_create_delay_comparison_plot(tmp_path):
    delay_df = pd.DataFrame({
        "line": ["S1", "U12", "18"],
        "departure_delay": [60, 120, 180],
    })
    output_path = tmp_path / "delay_comparison.png"

    create_delay_comparison_plot(delay_df, str(output_path))

    assert output_path.exists()
    assert output_path.stat().st_size > 0
