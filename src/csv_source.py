"""Reject malformed source files before they can replace a database snapshot."""

import csv
import hashlib
from pathlib import Path
from typing import Iterator

COLUMNS = (
    "hotel",
    "is_canceled",
    "lead_time",
    "arrival_date_year",
    "arrival_date_month",
    "arrival_date_week_number",
    "arrival_date_day_of_month",
    "stays_in_weekend_nights",
    "stays_in_week_nights",
    "adults",
    "children",
    "babies",
    "meal",
    "country",
    "market_segment",
    "distribution_channel",
    "is_repeated_guest",
    "previous_cancellations",
    "previous_bookings_not_canceled",
    "reserved_room_type",
    "assigned_room_type",
    "booking_changes",
    "deposit_type",
    "agent",
    "company",
    "days_in_waiting_list",
    "customer_type",
    "adr",
    "required_car_parking_spaces",
    "total_of_special_requests",
    "reservation_status",
    "reservation_status_date",
)


class SourceDataError(ValueError):
    """Distinguish source-file failures from connection or SQL failures."""


def source_sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def iter_source_rows(path: Path) -> Iterator[tuple[int, list[str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            header = next(reader, None)
            if header != list(COLUMNS):
                raise SourceDataError(
                    "CSV headers must match the original Hotel Booking Demand "
                    "column names and order. See src/csv_source.py:COLUMNS."
                )
            for record_number, row in enumerate(reader, start=2):
                if len(row) != len(COLUMNS):
                    raise SourceDataError(
                        f"CSV record {record_number} has {len(row)} fields; "
                        f"expected {len(COLUMNS)}."
                    )
                if any("\x00" in cell for cell in row):
                    raise SourceDataError(
                        f"CSV record {record_number} contains a NUL character."
                    )
                yield record_number, row
    except (csv.Error, UnicodeError) as exc:
        raise SourceDataError(f"CSV decoding/parsing failed: {exc}") from exc


def validate_source(path: Path) -> tuple[int, str]:
    before = source_sha256(path)
    count = sum(1 for _ in iter_source_rows(path))
    if count == 0:
        raise SourceDataError("The CSV has no booking records.")
    if source_sha256(path) != before:
        raise SourceDataError("The source CSV changed during validation.")
    return count, before

