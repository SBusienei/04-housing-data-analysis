"""Load and audit one atomic PostgreSQL snapshot without changing the source CSV."""

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import psycopg
from psycopg import sql
from psycopg.rows import class_row

from src.config import PROJECT_ROOT
from src.database import connect_database
from src.csv_source import (
    COLUMNS,
    SourceDataError,
    iter_source_rows,
    source_sha256,
    validate_source,
)

LOGGER = logging.getLogger(__name__)
SQL_DIRECTORY = PROJECT_ROOT / "sql" / "phase1"


@dataclass(frozen=True)
class QualitySummary:
    raw_rows: int
    retained_rows: int
    excluded_rows: int
    warning_rows: int
    zero_guest_rows: int
    unknown_guest_rows: int
    invalid_date_rows: int
    duplicate_excess_rows: int


def load_snapshot(
    connection: psycopg.Connection,
    source: Path,
    *,
    replace: bool = False,
) -> QualitySummary:
    expected_rows, checksum = validate_source(source)
    with connection.transaction():
        # Serialize this project's loaders without locking unrelated databases.
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext('hotel_booking.phase1_load'))"
        )
        connection.execute(
            (SQL_DIRECTORY / "01_schema.sql").read_text(encoding="utf-8")
        )
        existing = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM hotel_booking.bookings_raw)"
            " OR EXISTS (SELECT 1 FROM hotel_booking.bookings_quality)"
            " OR EXISTS (SELECT 1 FROM hotel_booking.load_audit)"
        ).fetchone()
        if existing is None:
            raise RuntimeError("Could not inspect the current database snapshot.")
        if existing[0] and not replace:
            raise ValueError(
                "A project snapshot already exists. Review it in DBeaver first. "
                "Use --replace only to replace this project's imported snapshot."
            )
        connection.execute(
            "TRUNCATE hotel_booking.bookings_quality, "
            "hotel_booking.bookings_raw, hotel_booking.load_audit"
        )
        copy_statement = sql.SQL(
            "COPY hotel_booking.bookings_raw ({}) FROM STDIN"
        ).format(
            sql.SQL(", ").join(
                sql.Identifier(column)
                for column in ("source_record_number", *COLUMNS)
            )
        )
        copied_rows = 0
        with connection.cursor().copy(copy_statement) as copy:
            for record_number, row in iter_source_rows(source):
                copy.write_row((record_number, *row))
                copied_rows += 1
        if copied_rows != expected_rows or source_sha256(source) != checksum:
            raise SourceDataError("The source CSV changed during import; rolled back.")

        connection.execute(
            (SQL_DIRECTORY / "02_clean.sql").read_text(encoding="utf-8")
        )
        with connection.cursor(row_factory=class_row(QualitySummary)) as cursor:
            cursor.execute(
                (SQL_DIRECTORY / "03_quality_report.sql").read_text(encoding="utf-8")
            )
            summary = cursor.fetchone()
        if summary is None:
            raise RuntimeError("The quality report did not return a summary.")
        if (
            summary.raw_rows != expected_rows
            or summary.raw_rows != summary.retained_rows + summary.excluded_rows
        ):
            raise RuntimeError("Raw, retained, and excluded row counts do not reconcile.")
        if summary.retained_rows == 0:
            raise SourceDataError(
                "No eligible bookings remain. Review the source and DATA.md; "
                "the database snapshot was not replaced."
            )
        connection.execute(
            "INSERT INTO hotel_booking.load_audit "
            "(source_filename, source_sha256, summary) VALUES (%s, %s, %s)",
            (source.name, checksum, psycopg.types.json.Jsonb(asdict(summary))),
        )
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        default=PROJECT_ROOT / "data" / "raw" / "hotel_bookings.csv",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace only the hotel_booking schema's imported snapshot atomically.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        with connect_database() as connection:
            summary = load_snapshot(connection, args.csv, replace=args.replace)
    except (OSError, ValueError, psycopg.Error, RuntimeError) as exc:
        LOGGER.error("Phase 1 import failed: %s", exc)
        return 1
    print(json.dumps(asdict(summary), indent=2))
    LOGGER.info(
        "Phase 1 snapshot committed. Review hotel_booking.load_audit and "
        "hotel_booking.bookings_quality in DBeaver before proceeding."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
