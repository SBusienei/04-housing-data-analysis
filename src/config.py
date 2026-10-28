"""Read local database settings without embedding credentials in project code."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str = field(repr=False)
    sslmode: str = "prefer"


def read_database_config(
    environment: Mapping[str, str] | None = None,
) -> DatabaseConfig:
    if environment is None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        environment = os.environ

    required = ("PGDATABASE", "PGUSER", "PGPASSWORD")
    missing = [key for key in required if not environment.get(key, "").strip()]
    if missing:
        raise ValueError(
            "Missing database settings: "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in your local credentials."
        )
    try:
        port = int(environment.get("PGPORT", "5432"))
    except ValueError as exc:
        raise ValueError("PGPORT must be a whole number.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PGPORT must be between 1 and 65535.")

    sslmode = environment.get("PGSSLMODE", "prefer")
    if sslmode not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
        raise ValueError("PGSSLMODE is not a supported PostgreSQL SSL mode.")

    return DatabaseConfig(
        host=environment.get("PGHOST", "localhost"),
        port=port,
        dbname=environment["PGDATABASE"],
        user=environment["PGUSER"],
        password=environment["PGPASSWORD"],
        sslmode=sslmode,
    )

