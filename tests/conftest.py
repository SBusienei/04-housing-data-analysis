"""Supply fictional CSV records without distributing or depending on Kaggle data."""

import csv
import os
from pathlib import Path
from typing import Callable, Iterator

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from src.csv_source import COLUMNS

CsvFactory = Callable[[list[dict[str, str]]], Path]


@pytest.fixture
def connection() -> Iterator[psycopg.Connection]:
    url = os.environ.get("HOTEL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set HOTEL_TEST_DATABASE_URL to a disposable PostgreSQL database.")
    if not conninfo_to_dict(url).get("dbname", "").startswith("hotel_booking_test_"):
        pytest.fail("The disposable test database name must start with hotel_booking_test_.")
    with psycopg.connect(url, autocommit=True, connect_timeout=10) as conn:
        if conn.execute(
            "SELECT to_regnamespace('hotel_booking') IS NOT NULL"
        ).fetchone()[0]:
            pytest.fail("The disposable test database must not contain hotel_booking.")
        with conn.transaction(force_rollback=True):
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            yield conn


@pytest.fixture
def booking() -> dict[str, str]:
    return {
        "hotel": "City Hotel",
        "is_canceled": "0",
        "lead_time": "30",
        "arrival_date_year": "2017",
        "arrival_date_month": "July",
        "arrival_date_week_number": "28",
        "arrival_date_day_of_month": "15",
        "stays_in_weekend_nights": "1",
        "stays_in_week_nights": "2",
        "adults": "2",
        "children": "0.0",
        "babies": "0",
        "meal": "BB",
        "country": "PRT",
        "market_segment": "Online TA",
        "distribution_channel": "TA/TO",
        "is_repeated_guest": "0",
        "previous_cancellations": "0",
        "previous_bookings_not_canceled": "0",
        "reserved_room_type": "A",
        "assigned_room_type": "A",
        "booking_changes": "0",
        "deposit_type": "No Deposit",
        "agent": "NULL",
        "company": "NULL",
        "days_in_waiting_list": "0",
        "customer_type": "Transient",
        "adr": "100.50",
        "required_car_parking_spaces": "0",
        "total_of_special_requests": "1",
        "reservation_status": "Check-Out",
        "reservation_status_date": "2017-07-18",
    }


@pytest.fixture
def csv_factory(tmp_path: Path) -> CsvFactory:
    sequence = 0

    def write(rows: list[dict[str, str]]) -> Path:
        nonlocal sequence
        sequence += 1
        path = tmp_path / f"fictional_bookings_{sequence}.csv"
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    return write
