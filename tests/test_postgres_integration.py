"""Verify the actual SQL pipeline only in an explicitly disposable test database."""

from datetime import date

import psycopg
import pytest

from src.csv_source import SourceDataError
from src.load_data import load_snapshot
from tests.conftest import CsvFactory

pytestmark = pytest.mark.integration


def test_real_import_schema_and_reconciliation(
    connection: psycopg.Connection,
    booking: dict[str, str],
    csv_factory: CsvFactory,
) -> None:
    summary = load_snapshot(
        connection, csv_factory([booking, {**booking, "is_canceled": "1"}])
    )
    assert summary.raw_rows == summary.retained_rows == 2
    assert summary.excluded_rows == 0
    assert connection.execute(
        "SELECT sum(is_canceled) FROM hotel_booking.bookings_clean"
    ).fetchone()[0] == 1
    clean = connection.execute(
        "SELECT children, arrival_date, agent, company "
        "FROM hotel_booking.bookings_clean ORDER BY source_record_number LIMIT 1"
    ).fetchone()
    assert clean == (0, date(2017, 7, 15), None, None)
    assert connection.execute(
        "SELECT summary ->> 'raw_rows' FROM hotel_booking.load_audit"
    ).fetchone()[0] == "2"
    assert connection.execute(
        "SELECT children FROM hotel_booking.bookings_raw LIMIT 1"
    ).fetchone()[0] == "0.0"


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"adults": "0", "children": "0.0", "babies": "0"}, "zero_guests"),
        ({"is_canceled": "2"}, "invalid_cancellation_label"),
        ({"is_canceled": ""}, "invalid_or_missing_integer:is_canceled"),
        ({"is_repeated_guest": "3"}, "invalid_repeat_label"),
        ({"lead_time": "-1"}, "negative_count:lead_time"),
        ({"adults": "-2"}, "negative_count:adults"),
        ({"children": "-1"}, "negative_count:children"),
        ({"children": "1.5"}, "invalid_children"),
        ({"children": "NaN"}, "invalid_children"),
        ({"lead_time": "2147483648"}, "invalid_or_missing_integer:lead_time"),
        ({"lead_time": "nonsense"}, "invalid_or_missing_integer:lead_time"),
        ({"arrival_date_month": "February", "arrival_date_day_of_month": "31"},
         "invalid_arrival_date"),
        ({"arrival_date_month": "not-a-month"}, "invalid_arrival_date"),
        ({"arrival_date_year": "0"}, "invalid_arrival_date"),
        ({"arrival_date_week_number": "54"}, "invalid_arrival_week"),
        ({"adr": "Infinity"}, "invalid_adr"),
        ({"adr": "invalid"}, "invalid_adr"),
        ({"hotel": " NULL "}, "missing_hotel"),
    ],
)
def test_invalid_records_are_audited_not_silently_deleted(
    connection: psycopg.Connection,
    booking: dict[str, str],
    csv_factory: CsvFactory,
    changes: dict[str, str],
    reason: str,
) -> None:
    summary = load_snapshot(connection, csv_factory([booking, {**booking, **changes}]))
    assert summary.raw_rows == 2
    assert summary.retained_rows == summary.excluded_rows == 1
    assert reason in connection.execute(
        "SELECT exclusion_reasons FROM hotel_booking.bookings_quality "
        "WHERE source_record_number = 3"
    ).fetchone()[0]
    assert connection.execute(
        "SELECT count(*) FROM hotel_booking.bookings_raw"
    ).fetchone()[0] == 2


def test_unknown_children_are_not_zero_guests(
    connection: psycopg.Connection,
    booking: dict[str, str],
    csv_factory: CsvFactory,
) -> None:
    summary = load_snapshot(
        connection, csv_factory([{**booking, "adults": "0", "children": ""}])
    )
    assert summary.retained_rows == summary.unknown_guest_rows == 1
    assert summary.zero_guest_rows == 0
    assert connection.execute(
        "SELECT children FROM hotel_booking.bookings_clean"
    ).fetchone()[0] is None


def test_identical_rows_are_retained_with_explicit_duplicate_counts(
    connection: psycopg.Connection,
    booking: dict[str, str],
    csv_factory: CsvFactory,
) -> None:
    summary = load_snapshot(connection, csv_factory([booking, booking, booking]))
    assert summary.retained_rows == 3
    assert summary.duplicate_excess_rows == 2
    assert connection.execute(
        "SELECT count(*) FROM hotel_booking.bookings_quality "
        "WHERE duplicate_group_size = 3"
    ).fetchone()[0] == 3


def test_review_only_fields_do_not_delete_bookings(
    connection: psycopg.Connection,
    booking: dict[str, str],
    csv_factory: CsvFactory,
) -> None:
    source = csv_factory([{
        **booking,
        "country": " NULL ",
        "adr": "-10",
        "stays_in_week_nights": "0",
        "stays_in_weekend_nights": "0",
        "reservation_status_date": "2017-02-31",
    }])
    summary = load_snapshot(connection, source)
    assert summary.retained_rows == 1
    warnings = connection.execute(
        "SELECT quality_warnings FROM hotel_booking.bookings_clean"
    ).fetchone()[0]
    assert {"missing_country", "negative_adr_review", "zero_nights_review",
            "invalid_status_date"} <= set(warnings)


def test_replace_is_explicit_and_late_failure_preserves_previous_snapshot(
    connection: psycopg.Connection,
    booking: dict[str, str],
    csv_factory: CsvFactory,
) -> None:
    source = csv_factory([booking])
    load_snapshot(connection, source)
    checksum = connection.execute(
        "SELECT source_sha256 FROM hotel_booking.load_audit"
    ).fetchone()[0]
    with pytest.raises(ValueError, match="--replace"):
        load_snapshot(connection, source)
    with pytest.raises(SourceDataError, match="No eligible"):
        load_snapshot(
            connection,
            csv_factory([{**booking, "is_canceled": "9"}]),
            replace=True,
        )
    assert connection.execute(
        "SELECT source_sha256 FROM hotel_booking.load_audit"
    ).fetchone()[0] == checksum
    assert connection.execute(
        "SELECT count(*) FROM hotel_booking.bookings_clean"
    ).fetchone()[0] == 1
    summary = load_snapshot(
        connection,
        csv_factory([booking, {**booking, "is_canceled": "1"}]),
        replace=True,
    )
    assert summary.retained_rows == 2


def test_source_change_after_copy_rolls_back(
    connection: psycopg.Connection,
    booking: dict[str, str],
    csv_factory: CsvFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = csv_factory([booking])
    monkeypatch.setattr("src.load_data.source_sha256", lambda path: "changed")
    with pytest.raises(SourceDataError, match="changed during import"):
        load_snapshot(connection, source)
    assert connection.execute(
        "SELECT to_regnamespace('hotel_booking')"
    ).fetchone()[0] is None
