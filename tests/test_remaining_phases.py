"""Exercise the later-phase scaffold with fictional records in an isolated database."""

import csv
import json
from datetime import date
from pathlib import Path

import psycopg
import pytest

from src.analyze import run_analysis
from src.config import PROJECT_ROOT
from src.export_dashboard import export_dashboard
from src.load_data import load_snapshot
from src.model import FEATURES, LEAKAGE_COLUMNS, train_models
from tests.conftest import CsvFactory

pytestmark = pytest.mark.integration


def fictional_periods(booking: dict[str, str]) -> list[dict[str, str]]:
    rows = []
    for year, month in [(2016, "July"), (2017, "April"), (2017, "July")]:
        for index in range(40):
            rows.append({
                **booking,
                "arrival_date_year": str(year),
                "arrival_date_month": month,
                "arrival_date_day_of_month": str(index // 2 + 1),
                "is_canceled": str(index % 2),
                "lead_time": str(10 + index * 3),
                "is_repeated_guest": str(int(index % 3 == 0)),
                "total_of_special_requests": str(index % 4),
                "distribution_channel": "Direct" if index % 2 == 0 else "TA/TO",
                "children": "" if index % 5 == 0 else "0.0",
                "market_segment": "" if index % 7 == 0 else "Online TA",
                "reservation_status": "Canceled" if index % 2 else "Check-Out",
            })
    return rows


def test_all_later_phases_on_fictional_data(
    connection: psycopg.Connection,
    booking: dict[str, str],
    csv_factory: CsvFactory,
    tmp_path: Path,
) -> None:
    source = csv_factory(fictional_periods(booking))
    load_snapshot(connection, source)
    phase2, phase3, phase4, phase5 = (
        tmp_path / name for name in ("phase2", "phase3", "phase4", "phase5")
    )
    run_analysis(connection, 2, phase2)
    with (phase2 / "01_overall.csv").open(newline="", encoding="utf-8") as file:
        overall = next(csv.DictReader(file))
    assert int(overall["bookings"]) == 120
    assert float(overall["cancellation_rate"]) == 0.5
    run_analysis(connection, 3, phase3)
    assert connection.execute(
        "SELECT count(*), count(DISTINCT source_record_number) "
        "FROM hotel_booking.booking_segments"
    ).fetchone() == (120, 120)

    with pytest.raises(ValueError, match="acknowledge"):
        train_models(connection, phase4, date(2017, 4, 1), date(2017, 7, 1))
    train_models(
        connection, phase4, date(2017, 4, 1), date(2017, 7, 1),
        acknowledge_snapshot_limitations=True,
    )
    manifest = json.loads((phase4 / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["partition_counts"] == {"training": 40, "validation": 40, "test": 40}
    assert manifest["features"] == list(FEATURES)
    assert not set(LEAKAGE_COLUMNS).intersection(manifest["features"])
    metrics = json.loads((phase4 / "test_metrics.json").read_text(encoding="utf-8"))
    assert set(metrics) == {"logistic_regression", "decision_tree", "training_rate_baseline"}
    assert all(value["bookings"] == 40 for value in metrics.values())

    export_dashboard(connection, phase4, phase5)
    with (phase5 / "risk_distribution.csv").open(newline="", encoding="utf-8") as file:
        risk = list(csv.DictReader(file))
    assert sum(int(row["bookings"]) for row in risk) == 40
    assert all(row["population"] == "final_test_later_arrivals" for row in risk)
    with (phase5 / "segment_comparison.csv").open(newline="", encoding="utf-8") as file:
        assert sum(int(row["bookings"]) for row in csv.DictReader(file)) == 120
    with (phase5 / "cancellation_trends.csv").open(newline="", encoding="utf-8") as file:
        assert sum(int(row["bookings"]) for row in csv.DictReader(file)) == 120

    predictions = phase4 / "test_predictions.csv"
    before = predictions.read_bytes()
    predictions.write_bytes(before + b"tampered")
    with pytest.raises(ValueError, match="changed after"):
        export_dashboard(connection, phase4, tmp_path / "tampered_export")
    predictions.write_bytes(before)
    load_snapshot(connection, csv_factory([booking]), replace=True)
    with pytest.raises(ValueError, match="different source snapshot"):
        export_dashboard(connection, phase4, tmp_path / "stale_export")


def test_segment_precedence_and_boundary_values(
    connection: psycopg.Connection,
    booking: dict[str, str],
    csv_factory: CsvFactory,
    tmp_path: Path,
) -> None:
    rows = [
        {**booking, "is_repeated_guest": "1", "lead_time": "90"},
        {**booking, "lead_time": "90"},
        {**booking, "lead_time": "89"},
        {**booking, "total_of_special_requests": "0"},
        {**booking, "lead_time": "90", "distribution_channel": "",
         "total_of_special_requests": "0"},
    ]
    load_snapshot(connection, csv_factory(rows))
    run_analysis(connection, 3, tmp_path / "segments")
    segments = connection.execute(
        "SELECT segment FROM hotel_booking.booking_segments ORDER BY source_record_number"
    ).fetchall()
    assert [row[0] for row in segments] == [
        "Returning guest", "Advance agency, no deposit", "Other with requests",
        "Other bookings", "Other bookings",
    ]
    query = (PROJECT_ROOT / "sql" / "phase2" / "03_lead_time.sql").read_text(encoding="utf-8")
    bands = connection.execute(query).fetchall()
    assert sum(row[1] for row in bands) == len(rows)
    assert {row[0] for row in bands} == {"02: 30-89 days", "03: 90+ days"}


def test_entirely_missing_training_numeric_input_is_not_silently_imputed(
    connection: psycopg.Connection,
    booking: dict[str, str],
    csv_factory: CsvFactory,
    tmp_path: Path,
) -> None:
    rows = [{**row, "children": ""} for row in fictional_periods(booking)]
    load_snapshot(connection, csv_factory(rows))
    output = tmp_path / "invalid_model"
    with pytest.raises(ValueError, match="entirely missing: children"):
        train_models(
            connection, output, date(2017, 4, 1), date(2017, 7, 1),
            acknowledge_snapshot_limitations=True,
        )
    assert not output.exists()


@pytest.mark.parametrize(
    ("risks", "expected"),
    [
        ([0.0, 0.3, 0.7, 1.0], [1, 1, 2]),
        ([0.2, 0.2, 0.2, 0.2], [4, 0, 0]),
    ],
)
def test_risk_band_boundaries_and_empty_bins(
    connection: psycopg.Connection, risks: list[float], expected: list[int]
) -> None:
    connection.execute(
        "CREATE TEMP TABLE model_test_predictions "
        "(source_record_number bigint, risk double precision, actual integer)"
    )
    with connection.cursor().copy(
        "COPY pg_temp.model_test_predictions FROM STDIN"
    ) as copy:
        for index, risk in enumerate(risks):
            copy.write_row((index, risk, index % 2))
    query = (PROJECT_ROOT / "sql" / "phase5" / "03_risk_distribution.sql").read_text(
        encoding="utf-8"
    )
    rows = connection.execute(query).fetchall()
    assert [row[3] for row in rows] == expected
    for row in rows:
        if row[3] == 0:
            assert row[4] is None
            assert row[5] is None
