"""Share connection and snapshot provenance across the manually run phases."""

import csv
import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg.pq import TransactionStatus

from src.config import read_database_config


@dataclass(frozen=True)
class Snapshot:
    source_filename: str
    source_sha256: str
    loaded_at: str
    cleaning_policy_version: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def connect_database() -> psycopg.Connection:
    config = read_database_config()
    return psycopg.connect(
        host=config.host,
        port=config.port,
        dbname=config.dbname,
        user=config.user,
        password=config.password,
        sslmode=config.sslmode,
        connect_timeout=10,
        autocommit=True,
    )


@contextmanager
def snapshot_transaction(connection: psycopg.Connection) -> Iterator[Snapshot]:
    top_level = connection.info.transaction_status == TransactionStatus.IDLE
    with connection.transaction():
        if top_level:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        elif connection.execute("SHOW transaction_isolation").fetchone()[0] != "repeatable read":
            raise ValueError("An existing transaction must use REPEATABLE READ isolation.")
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext('hotel_booking.phase1_load'))"
        )
        row = connection.execute(
            "SELECT source_filename, source_sha256, loaded_at, cleaning_policy_version "
            "FROM hotel_booking.load_audit"
        ).fetchone()
        if row is None:
            raise ValueError("No imported snapshot. Complete and review Phase 1 first.")
        yield Snapshot(row[0], row[1], row[2].isoformat(), row[3])


def query_to_csv(connection: psycopg.Connection, query: str, destination: Path) -> int:
    with connection.cursor() as cursor:
        cursor.execute(query)
        if cursor.description is None:
            raise ValueError("An export query must return named columns.")
        with destination.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(column.name for column in cursor.description)
            count = 0
            for row in cursor:
                writer.writerow(row)
                count += 1
    return count


def write_json(destination: Path, payload: dict[str, object]) -> None:
    destination.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
