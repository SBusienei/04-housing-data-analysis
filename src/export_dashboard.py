"""Export SQL summaries only when saved test predictions match the current data."""

import argparse
import csv
import json
import logging
from datetime import date
from pathlib import Path
from typing import Sequence

import psycopg

from src.artifacts import new_output_bundle
from src.config import PROJECT_ROOT
from src.csv_source import source_sha256
from src.database import (
    connect_database, query_to_csv, snapshot_transaction, write_json,
)
from src.model import PREDICTION_COLUMNS

LOGGER = logging.getLogger(__name__)


def export_dashboard(
    connection: psycopg.Connection, model_run: Path, output: Path
) -> None:
    manifest = json.loads((model_run / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("artifact_type") != "hotel_booking_model_v1":
        raise ValueError("The model-run folder must contain a supported Phase 4 manifest.")
    if manifest.get("primary_model") != "logistic_regression":
        raise ValueError("This export expects the prespecified logistic-regression primary.")
    test_start_text = manifest.get("test_start")
    if not isinstance(test_start_text, str):
        raise ValueError("The model manifest is missing test_start.")
    test_start = date.fromisoformat(test_start_text)
    predictions = model_run / "test_predictions.csv"
    if source_sha256(predictions) != manifest.get("prediction_sha256"):
        raise ValueError("Saved test predictions changed after modeling; regenerate the run.")

    with new_output_bundle(output) as staging:
        with snapshot_transaction(connection) as snapshot:
            if manifest.get("source_snapshot") != snapshot.as_dict():
                raise ValueError(
                    "Model predictions belong to a different source snapshot. "
                    "Rerun Phase 4 after a reload or policy change."
                )
            connection.execute(
                "CREATE TEMP TABLE model_test_predictions ("
                "source_record_number bigint PRIMARY KEY, arrival_date date NOT NULL,"
                "actual integer NOT NULL CHECK (actual IN (0,1)),"
                "risk double precision NOT NULL CHECK (risk >= 0 AND risk <= 1),"
                "model text NOT NULL CHECK (model = 'logistic_regression')"
                ") ON COMMIT DROP"
            )
            with predictions.open("r", encoding="utf-8", newline="") as source:
                reader = csv.reader(source, strict=True)
                if next(reader, None) != list(PREDICTION_COLUMNS):
                    raise ValueError("Unexpected test prediction CSV headers.")
                with connection.cursor().copy(
                    "COPY pg_temp.model_test_predictions FROM STDIN"
                ) as copy:
                    for row in reader:
                        if len(row) != len(PREDICTION_COLUMNS):
                            raise ValueError("Malformed test prediction CSV record.")
                        copy.write_row(row)
            counts = connection.execute(
                "SELECT (SELECT count(*) FROM hotel_booking.bookings_clean "
                "WHERE arrival_date >= %s),"
                "(SELECT count(*) FROM pg_temp.model_test_predictions),"
                "(SELECT count(*) FROM pg_temp.model_test_predictions p "
                "LEFT JOIN hotel_booking.bookings_clean b USING (source_record_number) "
                "WHERE b.source_record_number IS NULL OR b.arrival_date <> p.arrival_date "
                "OR b.is_canceled <> p.actual OR p.arrival_date < %s)",
                (test_start, test_start),
            ).fetchone()
            if counts is None or counts[0] == 0 or counts[0] != counts[1] or counts[2] != 0:
                raise ValueError("Predictions do not match the complete final-test population.")
            outputs = {}
            for name in ("01_cancellation_trends", "02_segment_comparison", "03_risk_distribution"):
                query = (
                    PROJECT_ROOT / "sql" / "phase5" / f"{name}.sql"
                ).read_text(encoding="utf-8")
                filename = name[3:] + ".csv"
                outputs[filename] = query_to_csv(connection, query, staging / filename)
            write_json(staging / "manifest.json", {
                "phase": 5,
                "source_snapshot": snapshot.as_dict(),
                "prediction_sha256": manifest["prediction_sha256"],
                "test_start": test_start.isoformat(),
                "primary_model": "logistic_regression",
                "output_rows": outputs,
                "populations": {
                    "cancellation_trends.csv": "All eligible historical bookings by arrival month.",
                    "segment_comparison.csv": "All eligible historical bookings.",
                    "risk_distribution.csv": "Final-test later-arrival bookings only.",
                },
                "rates": "Fractions between 0 and 1; empty risk bins have blank rates.",
            })


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-run", type=Path, default=PROJECT_ROOT / "data" / "processed" / "phase4",
    )
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "data" / "exports" / "phase5",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        with connect_database() as connection:
            export_dashboard(connection, args.model_run, args.output)
    except (OSError, ValueError, RuntimeError, csv.Error, psycopg.Error) as exc:
        LOGGER.error("Phase 5 failed: %s", exc)
        return 1
    LOGGER.info("Dashboard CSVs saved to %s. Build your dashboard separately.", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
