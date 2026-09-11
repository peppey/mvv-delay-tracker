import pandas as pd

from mvv_delay_tracker.analysis.plotting import (
    calculate_transport_mode_delays,
    classify_transport_mode,
    create_delay_comparison_plot,
    create_delay_heatmap,
    create_line_comparison_plot,
    filter_munich_lines,
)


def test_classify_transport_mode():
    assert classify_transport_mode("S1") == "S-Bahn"
    assert classify_transport_mode("S20") == "S-Bahn"
    assert classify_transport_mode("U1") == "U-Bahn"
    assert classify_transport_mode("U12") == "U-Bahn"
    assert classify_transport_mode("18") == "Tram/Bus"
    assert classify_transport_mode("X30") == "Tram/Bus"
    assert classify_transport_mode("N40") == "Tram/Bus"
    assert classify_transport_mode("RE1") is None


def test_calculate_transport_mode_delays():
    delay_df = pd.DataFrame({
        "line": ["S1", "U12", "18", "X30"],
        "departure_delay": [60, 120, 180, 240],
    })

    result = calculate_transport_mode_delays(delay_df)

    assert list(result["transport_mode"]) == [
        "S-Bahn",
        "U-Bahn",
        "Tram/Bus",
    ]
    assert list(result["delay_minutes"]) == [1.0, 2.0, 3.5]


def test_filter_munich_lines(tmp_path):
    lines_path = tmp_path / "munich_lines.csv"
    lines_path.write_text(
        "line,mode\nS6,S-Bahn\nU3,U-Bahn\n18,Tram\n"
    )
    delay_df = pd.DataFrame({
        "line": ["S6", "U3", "18", "SEV S6", "RE1"],
        "departure_delay": [60, 120, 180, 240, 300],
    })

    result = filter_munich_lines(delay_df, str(lines_path))

    assert list(result["line"]) == ["S6", "U3", "18"]


def test_create_delay_comparison_plot(tmp_path):
    delay_df = pd.DataFrame({
        "line": ["S1", "U12", "18"],
        "departure_delay": [60, 120, 180],
    })
    output_path = tmp_path / "delay_comparison.png"

    create_delay_comparison_plot(delay_df, str(output_path))

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_create_line_comparison_plot(tmp_path):
    delay_df = pd.DataFrame({
        "line": ["S1", "S1", "U1", "18", "18"],
        "departure_delay": [60, 180, 120, 60, 240],
    })
    output_path = tmp_path / "line_comparison.png"

    create_line_comparison_plot(delay_df, str(output_path))

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_create_delay_heatmap(tmp_path):
    delay_df = pd.DataFrame({
        "observation_timestamp": [
            "2026-09-07 08:00:00",
            "2026-09-08 17:00:00",
        ],
        "departure_delay": [60, 180],
    })
    output_path = tmp_path / "delay_heatmap.png"

    create_delay_heatmap(delay_df, str(output_path))

    assert output_path.exists()
    assert output_path.stat().st_size > 0
