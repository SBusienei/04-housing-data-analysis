"""Check configuration failures without connecting to a user's PostgreSQL server."""

import pytest

from src.config import read_database_config

SETTINGS = {
    "PGDATABASE": "hotel_bookings",
    "PGUSER": "example_user",
    "PGPASSWORD": "fictional-test-value",
}


def test_local_defaults_and_password_not_in_repr() -> None:
    config = read_database_config(SETTINGS)
    assert config.host == "localhost"
    assert config.port == 5432
    assert config.sslmode == "prefer"
    assert SETTINGS["PGPASSWORD"] not in repr(config)


@pytest.mark.parametrize("key", ["PGDATABASE", "PGUSER", "PGPASSWORD"])
def test_required_credentials(key: str) -> None:
    settings = {name: value for name, value in SETTINGS.items() if name != key}
    with pytest.raises(ValueError, match=key):
        read_database_config(settings)


@pytest.mark.parametrize("port", ["abc", "0", "65536", "1.5"])
def test_invalid_port(port: str) -> None:
    with pytest.raises(ValueError, match="PGPORT"):
        read_database_config({**SETTINGS, "PGPORT": port})


def test_invalid_ssl_mode() -> None:
    with pytest.raises(ValueError, match="PGSSLMODE"):
        read_database_config({**SETTINGS, "PGSSLMODE": "ignore"})

